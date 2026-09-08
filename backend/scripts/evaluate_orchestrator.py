"""Run the local orchestrator evaluation suite against the configured live LLM."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.auth import AuthContext
from core.config import get_settings
from core.db import connection
import core.orchestrator as orchestrator
import main as api_main
from main import ChatResponse


DEFAULT_DATASET = Path("/data/evaluations/orchestrator_questions.yaml")
VALID_AGENTS = frozenset({"iot", "manuals", "service", "orders"})


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Load local cases and reject expectations for retired agents."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = raw.get("cases") if isinstance(raw, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("The dataset must contain a non-empty 'cases' list.")

    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Every evaluation case must be an object.")
        required = {"id", "question", "context", "expected"}
        if not required.issubset(case):
            raise ValueError(f"Invalid evaluation case: {case!r}")
        expected = case["expected"]
        if not isinstance(expected, dict) or not isinstance(expected.get("agents", []), list):
            raise ValueError(f"Case {case['id']} must provide expected agents as a list.")
        unsupported = set(expected["agents"]) - VALID_AGENTS
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValueError(f"Case {case['id']} expects unsupported agents: {names}.")
    return cases


async def _machine_company(machine_id: str) -> str:
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT company_id FROM machines WHERE machine_id = %s", (machine_id,))
            row = await cursor.fetchone()
    if row is None:
        return "CMP-001"
    return str(row[0])


async def evaluation_user(case: dict[str, Any]) -> AuthContext:
    """Create the local role and tenant context declared by an evaluation case."""

    context = case["context"]
    if not isinstance(context, dict):
        raise ValueError(f"Case {case['id']} has an invalid context.")
    machine_id = context.get("machine_id")
    machine_id = machine_id if isinstance(machine_id, str) and machine_id.startswith("MCH-") else None
    company_id = context.get("user_company_id")
    if not isinstance(company_id, str) or not company_id:
        company_id = await _machine_company(machine_id) if machine_id else "CMP-001"
    user_id = context.get("user_id")
    visibility = context.get("user_visibility")
    return AuthContext(
        user_id=user_id if isinstance(user_id, str) and user_id else "ORCHESTRATOR-EVALUATION",
        company_id=company_id,
        visibility=visibility if isinstance(visibility, str) and visibility else "full",
    )


def expected_sources(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise singular and plural source expectations into one list."""

    expected = case["expected"]
    sources: list[dict[str, Any]] = []
    singular = expected.get("expected_source")
    if isinstance(singular, dict):
        sources.append(singular)
    plural = expected.get("expected_sources")
    if isinstance(plural, list):
        sources.extend(source for source in plural if isinstance(source, dict))
    return sources


def reported_sources(result: ChatResponse) -> list[dict[str, Any]]:
    """Keep only public manual citation metadata, never private chunk content."""

    sources: list[dict[str, Any]] = []
    for evidence in result.sources:
        file_name = evidence.citation.file
        page = evidence.citation.page
        if isinstance(file_name, str):
            sources.append({"file": file_name, "page": page if isinstance(page, int) else None})
    return sources


def missing_sources(expected: Iterable[dict[str, Any]], actual: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return expected file/page citations that do not appear in the result."""

    actual_sources = list(actual)
    missing: list[dict[str, Any]] = []
    for source in expected:
        file_name = source.get("file")
        page = source.get("page")
        if not isinstance(file_name, str):
            continue
        if not any(item["file"] == file_name and (not isinstance(page, int) or item["page"] == page) for item in actual_sources):
            missing.append({"file": file_name, "page": page if isinstance(page, int) else None})
    return missing


def review_contract(case: dict[str, Any]) -> dict[str, Any]:
    """Expose the semantic and safety criteria for human review without source passages."""

    expected = case["expected"]
    return {
        "expected_facts": expected.get("expected_facts"),
        "required_conditions": expected.get("required_conditions", []),
        "forbidden_claims": expected.get("forbidden_claims", []),
    }


def operation_trace(plan: Any) -> list[str]:
    """Return a compact agent.operation trace without request payloads."""

    if plan is None:
        return []
    return [f"{request.agent}.{request.operation}" for request in plan.requests]


async def handle_chat_with_trace(
    message: str,
    user: AuthContext,
    machine_id: str | None,
) -> tuple[ChatResponse | None, dict[str, Any], Exception | None]:
    """Run one user-visible chat request while recording plan and execution locally."""

    trace: dict[str, Any] = {"planner_action": None, "planned_operations": [], "executed_operations": []}
    original_decide = orchestrator.decide_question
    original_contextual_decide = orchestrator.decide_contextual_question
    original_execute = orchestrator._execute_plan

    async def capture_decision(*args: Any, **kwargs: Any) -> Any:
        decision = await original_decide(*args, **kwargs)
        trace["planner_action"] = decision.action
        trace["planned_operations"] = operation_trace(decision.plan)
        return decision

    async def capture_contextual_decision(*args: Any, **kwargs: Any) -> Any:
        decision = await original_contextual_decide(*args, **kwargs)
        trace["planner_action"] = decision.action
        trace["planned_operations"] = operation_trace(decision.plan)
        return decision

    async def capture_execute(*args: Any, **kwargs: Any) -> Any:
        plan = args[0]
        if not trace["planned_operations"]:
            trace["planned_operations"] = operation_trace(plan)
        bundle = await original_execute(*args, **kwargs)
        trace["executed_operations"] = [f"{result.agent}.{result.operation}" for result in bundle.results]
        return bundle

    orchestrator.decide_question = capture_decision
    orchestrator.decide_contextual_question = capture_contextual_decision
    orchestrator._execute_plan = capture_execute
    try:
        request = api_main.ChatRequest(message=message, machine_id=machine_id)
        return await api_main.chat(request, user), trace, None
    except Exception as error:
        return None, trace, error
    finally:
        orchestrator.decide_question = original_decide
        orchestrator.decide_contextual_question = original_contextual_decide
        orchestrator._execute_plan = original_execute


async def evaluate_case(case: dict[str, Any], run_number: int) -> dict[str, Any]:
    """Execute one case and retain deterministic checks plus review criteria."""

    context = case["context"]
    machine_id = context.get("machine_id") if isinstance(context, dict) else None
    machine_id = machine_id if isinstance(machine_id, str) and machine_id.startswith("MCH-") else None
    started = time.perf_counter()
    result, trace, error = await handle_chat_with_trace(
        str(case["question"]), await evaluation_user(case), machine_id,
    )
    if error is not None:
        return {
            "id": case["id"],
            "run": run_number,
            "category": case.get("category"),
            "question": case["question"],
            "status": "execution_error",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error_type": type(error).__name__,
            "error": str(error),
            "trace": trace,
            "review": review_contract(case),
        }

    assert result is not None
    expected_agents = list(case["expected"].get("agents", []))
    actual_agents = result.agent or []
    missing_agents = sorted(set(expected_agents) - set(actual_agents))
    sources = reported_sources(result)
    absent_sources = missing_sources(expected_sources(case), sources)
    problems: list[str] = []
    if missing_agents:
        problems.append(f"Missing expected agents: {', '.join(missing_agents)}.")
    if absent_sources:
        problems.append("Missing expected manual citations.")
    return {
        "id": case["id"],
        "run": run_number,
        "category": case.get("category"),
        "question": case["question"],
        "status": "completed",
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "expected_agents": expected_agents,
        "actual_agents": actual_agents,
        "missing_agents": missing_agents,
        "reported_manual_sources": sources,
        "missing_expected_sources": absent_sources,
        "answer": result.answer,
        "trace": trace,
        "automatic_checks": {"status": "failed" if problems else "passed", "problems": problems},
        "review": review_contract(case),
    }


def build_report(results: list[dict[str, Any]], case_count: int, repetitions: int) -> dict[str, Any]:
    """Summarise live execution while keeping case-level failures inspectable."""

    settings = get_settings()
    errors = [result for result in results if result["status"] == "execution_error"]
    failed_checks = [
        result for result in results
        if result["status"] == "completed" and result["automatic_checks"]["status"] == "failed"
    ]
    completed = [result for result in results if result["status"] != "execution_error"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": {"base_url": settings.llm_base_url, "model": settings.llm_model},
        "case_count": case_count,
        "repetitions": repetitions,
        "metrics": {
            "attempts": len(results),
            "completed": len(completed),
            "execution_errors": len(errors),
            "automatic_check_failures": len(failed_checks),
            "automatic_check_pass_rate": round(
                0 if not completed else (len(completed) - len(failed_checks)) / len(completed), 3
            ),
            "mean_latency_ms": round(sum(result["latency_ms"] for result in completed) / len(completed), 1) if completed else None,
        },
        "problem_cases": [
            result["id"] for result in results
            if result["status"] == "execution_error" or result["automatic_checks"]["status"] == "failed"
        ],
        "cases": results,
    }


def _markdown_list(items: Iterable[str]) -> str:
    return "None." if not items else "\n".join(f"- {item}" for item in items)


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render a local human-review report with trace and chatbot response for every case."""

    provider = report["provider"]
    metrics = report["metrics"]
    lines = [
        "# AROL orchestrator evaluation",
        "",
        f"- Model: `{provider['model']}`",
        f"- Base URL: `{provider['base_url']}`",
        f"- Attempts: {metrics['attempts']}",
        f"- Completed: {metrics['completed']}",
        f"- Execution errors: {metrics['execution_errors']}",
        f"- Automatic check failures: {metrics['automatic_check_failures']}",
    ]
    for case in report["cases"]:
        lines.extend(["", f"## {case['id']}", "", f"- Category: `{case.get('category')}`", f"- Status: `{case['status']}`", f"- Latency: {case['latency_ms']} ms"])
        trace = case["trace"]
        lines.append(f"- Planner action: `{trace['planner_action']}`")
        lines.append("- Planned operations:")
        lines.append(_markdown_list(trace["planned_operations"]))
        lines.append("- Executed operations:")
        lines.append(_markdown_list(trace["executed_operations"]))
        if case["status"] == "execution_error":
            lines.extend([f"- Error: `{case['error_type']}: {case['error']}`", "- Chatbot response: unavailable because execution failed."])
            continue
        automatic = case["automatic_checks"]
        lines.append(f"- Automatic checks: `{automatic['status']}`")
        lines.append("- Automatic findings:")
        lines.append(_markdown_list(automatic["problems"]))
        lines.extend(["", "### Chatbot response", "", case["answer"], "", "### Manual review checklist", ""])
        lines.append("Required conditions:")
        lines.append(_markdown_list(case["review"]["required_conditions"]))
        lines.append("Forbidden claims:")
        lines.append(_markdown_list(case["review"]["forbidden_claims"]))
    return "\n".join(lines) + "\n"


async def run(cases: list[dict[str, Any]], repetitions: int) -> dict[str, Any]:
    """Run cases sequentially to keep provider usage and failures attributable."""

    results = [await evaluate_case(case, run_number) for run_number in range(1, repetitions + 1) for case in cases]
    return build_report(results, len(cases), repetitions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the live AROL orchestrator against local YAML cases.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Ignored local YAML dataset path")
    parser.add_argument("--output", type=Path, help="Optional local JSON report path")
    parser.add_argument("--markdown-output", type=Path, help="Optional local Markdown report for human review")
    parser.add_argument("--repetitions", type=int, default=1, help="Sequential runs for each evaluation case")
    parser.add_argument("--case", action="append", dest="case_ids", help="Evaluate only one case id; repeat as needed")
    args = parser.parse_args()
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be at least 1.")
    if not args.dataset.is_file():
        raise SystemExit(f"Dataset not found: {args.dataset}")

    cases = load_cases(args.dataset)
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case["id"] in selected]
        missing = selected - {case["id"] for case in cases}
        if missing:
            raise SystemExit(f"Unknown case ids: {', '.join(sorted(missing))}")
    report = asyncio.run(run(cases, args.repetitions))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Local report written to {args.output}")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown_report(report), encoding="utf-8")
        print(f"Local Markdown report written to {args.markdown_output}")
    print(json.dumps({"provider": report["provider"], "metrics": report["metrics"], "problem_cases": report["problem_cases"]}, indent=2))


if __name__ == "__main__":
    main()
