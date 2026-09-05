"""Intent routing and response composition for the conversational API."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any

from agents.troubleshoot import investigate
from core.alarm_codes import alarm_meaning, normalise_alarm_code
from core.auth import AuthContext
from core.business_time import BUSINESS_TODAY
from core.contracts import AgentRequest, AgentResult, OrchestrationPlan, PlannerDecision
from core.config import get_settings
from core.llm import generate_chat_reply
from core.operation_registry import OPERATION_REGISTRY, OperationContext
from core.planner import decide_question


class MissingMachineContextError(ValueError):
    """A machine-specific intent was received without a QR/machine identifier."""


@dataclass(frozen=True)
class OrchestrationResult:
    agent: str
    answer: str
    manual_evidence: list[dict[str, Any]] | None = None
    structured_data: dict[str, Any] | None = None


@dataclass(frozen=True)
class EvidenceBundle:
    """Agent results kept separate for composition and for the existing UI."""

    results: list[AgentResult]
    composer_evidence: list[dict[str, Any]]
    structured_data: dict[str, Any]


MACHINE_PATTERN = re.compile(r"\bMCH-[A-Z0-9-]+\b", re.IGNORECASE)
ALARM_CODE_PATTERN = re.compile(r"\bAL\d{3}_[A-Z0-9_]+\b", re.IGNORECASE)


def classify_intent(message: str) -> str:
    """Route English and Italian questions before invoking the LLM."""

    text = message.casefold()
    if ALARM_CODE_PATTERN.search(message) and any(
        term in text for term in ("how many", "number of", "count", "quante", "quanti", "conteggio")
    ):
        return "iot"
    if ALARM_CODE_PATTERN.search(message):
        return "alarm_guidance"
    maintenance_due_terms = (
        "maintenance due", "due maintenance", "overdue maintenance", "next maintenance",
        "maintenance threshold", "operating hours", "working hours", "ore di lavoro",
        "ore operative", "manutenzione dovuta", "manutenzione scaduta", "soglia manutenzione",
        "prossima manutenzione", "quando è prevista", "due", "dovuta", "scaduta", "scadenza",
    )
    if any(term in text for term in ("maintenance", "manutenzione")) and any(
        term in text for term in maintenance_due_terms
    ):
        return "maintenance_due"
    maintenance_manual_terms = (
        "periodic", "interval", "procedure", "required", "requirement", "due",
        "scheduled maintenance", "how to maintain", "maintenance schedule",
        "periodic maintenance", "intervallo", "procedura", "richiesto", "scadenza",
    )
    if any(
        word in text
        for word in (
            "why", "diagnos", "diagnosis", "cause", "problem", "troubleshoot",
            "perché", "perche", "causa", "problema",
        )
    ):
        return "troubleshoot"
    if any(
        word in text
        for word in (
            "manual", "instruction", "configuration", "safety", "installation",
            "assembly", "lubricat", "mechanical", "pneumatic", "pressur", "operation",
            "manuale", "istruzioni", "configurazione", "sicurezza", "installazione",
            "montaggio", "lubrificazione", "meccanico", "pneumatico", "operazione",
        )
    ) or ("maintenance" in text and any(term in text for term in maintenance_manual_terms)):
        return "manuals"
    if any(
        word in text
        for word in (
            "alarm", "telemetr", "production", "uptime", "temperature", "operational status",
            "allarm", "produzion", "temperatura", "stato operativo",
        )
    ):
        return "iot"
    if any(
        word in text
        for word in ("maintenance", "ticket", "intervention", "service", "manutenz", "intervento")
    ):
        return "service"
    if any(
        word in text
        for word in (
            "order", "quote", "price", "discount", "shipment", "cost", "invoice", "purchase",
            "ordine", "ordini", "preventiv", "quotazione", "prezzo", "sconto", "spedizion",
            "costo", "costa", "costat", "fattura", "acquist",
        )
    ):
        return "orders"
    return "general"


def _iso_periods(message: str) -> list[tuple[datetime, datetime]]:
    """Extract pairs of inclusive ISO dates for the current deterministic router."""

    values = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", message)
    periods: list[tuple[datetime, datetime]] = []
    for index in range(0, len(values) - 1, 2):
        start_date = datetime.fromisoformat(values[index]).date()
        end_date = datetime.fromisoformat(values[index + 1]).date()
        periods.append(
            (
                datetime.combine(start_date, time.min, tzinfo=timezone.utc),
                datetime.combine(end_date, time.max, tzinfo=timezone.utc),
            )
        )
    return periods


def _deterministic_plan(intent: str, message: str) -> OrchestrationPlan | None:
    """Temporary planner that maps the legacy router to registered operations.

    It deliberately produces the same strict ``OrchestrationPlan`` that the
    future LLM planner will produce.  Therefore replacing this bridge will not
    change authorisation, parameter validation, agent invocation, or UI data.
    """

    text = message.casefold()
    periods = _iso_periods(message)
    start_time, end_time = periods[0] if periods else (None, None)
    code_match = ALARM_CODE_PATTERN.search(message)
    alarm_code = code_match.group(0).upper() if code_match else None

    if intent == "iot":
        alarm_parameters = {"start_time": start_time, "end_time": end_time, "alarm_code": alarm_code}
        count_terms = ("how many", "number of", "count", "quante", "quanti", "conteggio")
        summary_terms = ("most frequent", "recurring", "repeated", "group", "frequency", "più frequ", "ricorrent")
        telemetry_terms = ("telemetr", "temperature", "energy", "uptime", "production", "temperatura", "energia", "produzion")
        statistic_terms = ("average", "mean", "minimum", "maximum", "total", "trend", "media", "minim", "massim", "totale", "andamento")

        if alarm_code and any(term in text for term in count_terms):
            requests = [AgentRequest(agent="iot", operation="count_alarms", parameters=alarm_parameters)]
        elif "alarm" in text or "allarm" in text:
            operation = "alarm_summary" if any(term in text for term in summary_terms) else "recent_alarms"
            requests = [AgentRequest(agent="iot", operation=operation, parameters={**alarm_parameters, "limit": 20})]
        elif any(term in text for term in telemetry_terms) and any(term in text for term in statistic_terms):
            if len(periods) >= 2 and any(term in text for term in ("compare", "comparison", "confront")):
                requests = [AgentRequest(
                    agent="iot",
                    operation="compare_telemetry_periods",
                    parameters={
                        "first_start": periods[0][0], "first_end": periods[0][1],
                        "second_start": periods[1][0], "second_end": periods[1][1],
                    },
                )]
            else:
                requests = [AgentRequest(
                    agent="iot",
                    operation="telemetry_summary",
                    parameters={"start_time": start_time, "end_time": end_time},
                )]
        else:
            requests = [
                AgentRequest(agent="iot", operation="recent_alarms", parameters={**alarm_parameters, "limit": 20}),
                AgentRequest(agent="iot", operation="telemetry", parameters={"start_time": start_time, "end_time": end_time, "limit": 20}),
            ]
        return OrchestrationPlan(requests=requests)

    if intent == "alarm_guidance" and alarm_code:
        return _alarm_guidance_plan(alarm_code, limit=5)

    if intent == "manuals":
        return OrchestrationPlan(
            requests=[AgentRequest(agent="manuals", operation="search", parameters={"query": message, "limit": 5})],
        )
    if intent == "service":
        return OrchestrationPlan(
            requests=[AgentRequest(agent="service", operation="maintenance_tickets", parameters={"limit": 10})],
        )
    if intent == "maintenance_due":
        return OrchestrationPlan(
            requests=[AgentRequest(agent="service", operation="observed_maintenance_plan")],
        )
    if intent == "orders":
        return OrchestrationPlan(
            requests=[
                AgentRequest(agent="orders", operation="orders", parameters={"limit": 10}),
                AgentRequest(agent="orders", operation="quotes", parameters={"limit": 10}),
            ],
        )
    return None


def _plan_for_chat(intent: str, message: str) -> OrchestrationPlan:
    """Build the temporary deterministic fallback while the planner is disabled."""

    plan = _deterministic_plan(intent, message)
    assert plan is not None
    return plan


def _machine_id(message: str, machine_id: str | None) -> str | None:
    if machine_id and machine_id.strip():
        return machine_id.strip()
    match = MACHINE_PATTERN.search(message)
    return match.group(0).upper() if match else None


def _require_machine(message: str, machine_id: str | None) -> str:
    resolved = _machine_id(message, machine_id)
    if resolved is None:
        raise MissingMachineContextError(
            "Select a machine first, or include its ID (for example, MCH-0001) in your question."
        )
    return resolved


async def _execute_plan(
    plan: OrchestrationPlan,
    message: str,
    machine_id: str | None,
    user: AuthContext,
) -> EvidenceBundle:
    """Execute only allow-listed operations and retain each result boundary."""

    target = (
        _require_machine(message, machine_id)
        if OPERATION_REGISTRY.plan_requires_machine_context(plan.requests)
        else None
    )
    context = OperationContext(user=user, machine_id=target)
    results = [await OPERATION_REGISTRY.execute(request, context) for request in plan.requests]

    structured_data: dict[str, Any] = {}
    composer_evidence: list[dict[str, Any]] = []
    for result in results:
        if result.structured_data:
            structured_data.update(result.structured_data)
        composer_evidence.append(
            {
                "agent": result.agent,
                "operation": result.operation,
                "evidence": result.evidence,
                "sources": [source.model_dump() for source in result.sources],
                "warnings": result.warnings,
            }
        )
    return EvidenceBundle(results, composer_evidence, structured_data)


def _alarm_guidance_plan(alarm_code: str, limit: int) -> OrchestrationPlan:
    """Build the two registered evidence requests for one alarm code."""

    normalized_code = normalise_alarm_code(alarm_code)
    return OrchestrationPlan(
        requests=[
            AgentRequest(
                agent="iot",
                operation="alarm_guidance_context",
                parameters={"alarm_code": normalized_code, "limit": limit},
            ),
            AgentRequest(
                agent="manuals",
                operation="search",
                parameters={
                    "query": (
                        f"{normalized_code} {alarm_meaning(normalized_code)} "
                        "cause remedy troubleshooting"
                    ),
                    "limit": limit,
                },
            ),
        ],
    )


async def retrieve_alarm_guidance_evidence(
    machine_id: str,
    alarm_code: str,
    user: AuthContext,
    limit: int,
) -> EvidenceBundle:
    """Retrieve alarm guidance through the same registered operations as chat."""

    return await _execute_plan(_alarm_guidance_plan(alarm_code, limit), "", machine_id, user)


def _manual_reference(chunk: dict[str, Any]) -> str:
    """Format one local-only manual citation for a chat response."""

    return f"{chunk['file']}, p. {chunk['page']}, sezione {chunk['section']}"


async def _compose_evidence_answer(message: str, bundle: EvidenceBundle) -> str:
    """Compose a grounded answer from bounded, authorised agent evidence."""

    prompt = (
        f"User question: {message}\n\n"
        "Use only the following evidence retrieved by authorised backend tools. "
        "If it is empty, say that no matching records were found. Do not invent values. "
        "Answer only in English and mention relevant IDs, statuses, or manual citations when useful. "
        f"Use {BUSINESS_TODAY.isoformat()} as today's date when interpreting "
        "quote expiry, open items, or overdue work.\n\n"
        f"Evidence retrieved by the authorised agents:\n"
        f"{json.dumps(bundle.composer_evidence, default=str, ensure_ascii=False)}"
    )
    system_prompt = (
        "You are the AROL Customer Platform assistant. "
        "The backend has already enforced authentication, company scope, and role permissions. "
        "Summarise only the supplied evidence; never reveal or infer data outside it. "
        "Manual evidence contains bounded excerpts and citations, never raw PDF chunks. "
        "For maintenance observations, treat observed productive hours as a bounded telemetry window, "
        "not as a lifetime counter; do not claim a threshold proves maintenance is currently due or completed."
    )
    return await generate_chat_reply(prompt, system_prompt=system_prompt)


def _local_manual_answer(evidence: dict[str, Any]) -> str:
    """Compose a manual answer locally; manuals must not leave this backend."""

    chunks = evidence["manual_evidence"]
    if not chunks:
        return "I could not find relevant passages in this machine's manual."

    return (
        f"I found {len(chunks)} relevant manual source(s). "
        "Review the structured sources below and open the cited page for the complete procedure."
    )


def _local_troubleshoot_answer(evidence: dict[str, Any]) -> str:
    """Return diagnostic evidence locally, never exposing manual text to the LLM."""

    alarms = evidence["alarms"]
    patterns = evidence.get("repeated_alarm_patterns", [])
    tickets = evidence["maintenance_tickets"]
    top_patterns = patterns[:3]
    pattern_summary = (
        "; ".join(
            f"{alarm_meaning(pattern['alarm_code'])} ({pattern['alarm_code']}, "
            f"{pattern['occurrences']} occurrences, latest status: {pattern['latest_status']})"
            for pattern in top_patterns
        )
        if top_patterns
        else "No alarm code has occurred more than once in the available alarm history."
    )
    cap_related = [pattern for pattern in patterns if "CAPS" in pattern["alarm_code"]]
    pattern_interpretation = (
        "Most recurring conditions concern cap feeding or cap checking. This points to a repeated issue in that area, "
        "but the recorded alarms alone cannot confirm its root cause."
        if len(cap_related) > len(patterns) / 2
        else "The recorded alarms do not point to one dominant subsystem, so the data alone cannot confirm a root cause."
    )
    latest_snapshot = evidence["telemetry"][0] if evidence["telemetry"] else None
    telemetry_summary = (
        f"The latest telemetry snapshot is {latest_snapshot['operational_status']} "
        f"at {latest_snapshot['timestamp'].isoformat()}, with {latest_snapshot['alarm_count']} alarm(s) in that hour."
        if latest_snapshot
        else "No recent telemetry snapshots are available."
    )
    ticket_summary = (
        "; ".join(
            f"{ticket['ticket_id']} ({ticket['ticket_status']}, priorità {ticket['priority']})"
            for ticket in tickets
        )
        if tickets
        else "no recent tickets"
    )
    manual_answer = _local_manual_answer(
        {"manual_evidence": evidence["manual_evidence"]}
    )
    return (
        f"Repeated alarm analysis for {evidence['machine_id']}: {len(patterns)} recurring condition(s) found. "
        f"Most frequent: {pattern_summary}.\n{pattern_interpretation}\n"
        f"{telemetry_summary} Maintenance tickets: {ticket_summary}.\n\n"
        "This identifies recurring conditions from the recorded data; the manual sources below provide the machine-specific checks and remedies, not a confirmed root cause.\n\n"
        f"{manual_answer}"
    )


async def handle_chat(
    message: str,
    user: AuthContext,
    machine_id: str | None = None,
) -> OrchestrationResult:
    """Route a chat message, collect authorised evidence, and compose an answer."""

    intent = classify_intent(message)
    planner_enabled = get_settings().llm_planner_enabled
    planner_decision = await decide_question(message) if planner_enabled else None
    if planner_decision is not None and planner_decision.action == "answer_without_evidence":
        return OrchestrationResult("general", await generate_chat_reply(message))
    if intent == "general" and planner_decision is None:
        return OrchestrationResult("general", await generate_chat_reply(message))

    # Troubleshooting remains a legacy diagnostic workflow until all of its
    # evidence operations are registered. Alarm guidance already uses the
    # regular multi-agent execution path below.
    if intent == "troubleshoot":
        target = _require_machine(message, machine_id)
        evidence = await investigate(target, message, user, 5)
        return OrchestrationResult(
            "troubleshoot",
            _local_troubleshoot_answer(evidence),
            manual_evidence=evidence["manual_evidence"],
            structured_data={
                "machine_id": evidence["machine_id"],
                "alarms": evidence["alarms"],
                "alarm_patterns": evidence.get("repeated_alarm_patterns", []),
                "telemetry": evidence["telemetry"],
                "maintenance_tickets": evidence["maintenance_tickets"],
            },
        )
    if intent == "alarm_guidance":
        plan = planner_decision.plan if planner_decision is not None else _plan_for_chat(intent, message)
        assert plan is not None
        bundle = await _execute_plan(plan, message, machine_id, user)
        manual_result = next(
            (
                result
                for result in bundle.results
                if result.agent == "manuals" and result.operation == "search"
            ),
            None,
        )
        return OrchestrationResult(
            "alarm_guidance",
            await _compose_evidence_answer(message, bundle),
            manual_evidence=(
                manual_result.evidence.get("manual_evidence") if manual_result is not None else None
            ),
            structured_data=bundle.structured_data,
        )

    plan = planner_decision.plan if planner_decision is not None else _plan_for_chat(intent, message)
    assert plan is not None
    bundle = await _execute_plan(plan, message, machine_id, user)
    # The manuals agent removes raw PDF chunks before an EvidenceBundle is
    # composed. Only bounded excerpts and citations may reach the composer.
    if intent == "manuals":
        evidence = bundle.results[0].evidence
        return OrchestrationResult(
            "manuals",
            await _compose_evidence_answer(message, bundle),
            manual_evidence=evidence["manual_evidence"],
        )
    if intent == "maintenance_due":
        return OrchestrationResult(
            "maintenance_due",
            await _compose_evidence_answer(message, bundle),
            structured_data=bundle.structured_data,
        )

    return OrchestrationResult(
        intent,
        await _compose_evidence_answer(message, bundle),
        structured_data=bundle.structured_data,
    )
