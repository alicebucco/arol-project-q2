"""Evaluate local manual retrieval against a local, non-publishable golden dataset."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.manuals import search as search_manual
from core.auth import AuthContext
from core.db import connection


DEFAULT_DATASET = Path("/data/evaluations/rag_golden_dataset.json")


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Load and validate the minimum contract for local evaluation cases."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("The dataset must contain a non-empty 'cases' list.")
    required = {"id", "question", "machine_id", "expected_file", "expected_answer_contains"}
    for case in cases:
        if not isinstance(case, dict) or not required.issubset(case):
            raise ValueError(f"Invalid evaluation case: {case!r}")
        if not isinstance(case["expected_answer_contains"], list):
            raise ValueError(f"Case {case['id']} must provide keyword expectations as a list.")
    return cases


async def evaluation_user(machine_id: str) -> AuthContext:
    """Create a local full-visibility context for the machine's own company."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT company_id FROM machines WHERE machine_id = %s", (machine_id,))
            row = await cursor.fetchone()
    if row is None:
        raise LookupError(f"Machine {machine_id!r} does not exist in the local database.")
    return AuthContext("RAG-EVALUATION", row[0], "full")


def keyword_coverage(results: list[dict[str, Any]], expected_keywords: list[str]) -> tuple[float, list[str]]:
    """Measure how many expected answer concepts occur in the retrieved chunks."""

    if not expected_keywords:
        return 1.0, []
    evidence = " ".join(str(result.get("content", "")) for result in results).casefold()
    found = [keyword for keyword in expected_keywords if keyword.casefold() in evidence]
    return len(found) / len(expected_keywords), found


async def evaluate_case(case: dict[str, Any], top_k: int, page_tolerance: int) -> dict[str, Any]:
    """Run one local retrieval query and retain citations and quantitative signals."""

    user = await evaluation_user(str(case["machine_id"]))
    results = await search_manual(str(case["machine_id"]), str(case["question"]), user, top_k)
    expected_file = str(case["expected_file"])
    file_rank = next((index + 1 for index, result in enumerate(results) if result.get("file") == expected_file), None)
    expected_page = case.get("expected_page")
    page_rank = None
    tolerant_page_rank = None
    if isinstance(expected_page, int):
        page_rank = next(
            (
                index + 1
                for index, result in enumerate(results)
                if result.get("file") == expected_file and result.get("page") == expected_page
            ),
            None,
        )
        tolerant_page_rank = next(
            (
                index + 1
                for index, result in enumerate(results)
                if result.get("file") == expected_file and abs(int(result.get("page", -1)) - expected_page) <= page_tolerance
            ),
            None,
        )
    coverage, found_keywords = keyword_coverage(results, list(case["expected_answer_contains"]))

    return {
        "id": case["id"],
        "question": case["question"],
        "machine_id": case["machine_id"],
        "expected_file": expected_file,
        "expected_page": expected_page,
        "file_rank": file_rank,
        "page_rank": page_rank,
        "page_rank_within_tolerance": tolerant_page_rank,
        "keyword_coverage": round(coverage, 3),
        "found_keywords": found_keywords,
        "retrieved_sources": [
            {"file": result.get("file"), "page": result.get("page"), "section": result.get("section"), "relevance": result.get("relevance")}
            for result in results
        ],
    }


def build_report(results: list[dict[str, Any]], top_k: int, page_tolerance: int) -> dict[str, Any]:
    """Aggregate retrieval metrics without storing manual text in the report."""

    page_results = [result for result in results if isinstance(result["expected_page"], int)]
    return {
        "top_k": top_k,
        "page_tolerance": page_tolerance,
        "case_count": len(results),
        "metrics": {
            "file_recall_at_k": round(mean(result["file_rank"] is not None for result in results), 3),
            "mean_reciprocal_rank": round(mean(0 if result["file_rank"] is None else 1 / result["file_rank"] for result in results), 3),
            "mean_keyword_coverage": round(mean(result["keyword_coverage"] for result in results), 3),
            "page_recall_at_k": None if not page_results else round(mean(result["page_rank"] is not None for result in page_results), 3),
            "page_recall_at_k_within_tolerance": None if not page_results else round(mean(result["page_rank_within_tolerance"] is not None for result in page_results), 3),
            "page_case_count": len(page_results),
        },
        "cases": results,
    }


async def run(dataset: Path, top_k: int, page_tolerance: int) -> dict[str, Any]:
    cases = load_cases(dataset)
    results = [await evaluate_case(case, top_k, page_tolerance) for case in cases]
    return build_report(results, top_k, page_tolerance)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate local RAG retrieval against a local golden dataset.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Ignored local JSON dataset path")
    parser.add_argument("--top-k", type=int, default=3, help="Number of retrieved sources to evaluate")
    parser.add_argument("--page-tolerance", type=int, default=2, help="Adjacent PDF pages accepted by the tolerant page metric")
    parser.add_argument("--output", type=Path, help="Optional local JSON report path")
    args = parser.parse_args()
    if args.top_k < 1 or args.page_tolerance < 0:
        raise SystemExit("--top-k must be at least 1 and --page-tolerance cannot be negative.")
    if not args.dataset.is_file():
        raise SystemExit(f"Dataset not found: {args.dataset}")

    report = asyncio.run(run(args.dataset, args.top_k, args.page_tolerance))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Local report written to {args.output}")
    print(json.dumps({"case_count": report["case_count"], "metrics": report["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
