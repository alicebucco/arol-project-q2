"""Intent routing and response composition for the conversational API."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any

from agents.iot import (
    alarm_summary,
    compare_telemetry_periods,
    count_alarms,
    recent_alarms,
    telemetry,
    telemetry_summary,
)
from agents.alarms import alarm_meaning, explain as explain_alarm
from agents.manuals import ManualsUnavailableError, search as search_manual
from agents.orders import orders, quotes
from agents.service import maintenance_tickets, observed_maintenance_plan
from agents.troubleshoot import investigate
from core.auth import AuthContext
from core.business_time import BUSINESS_TODAY
from core.data_access import MachineNotFoundError
from core.llm import generate_chat_reply


class MissingMachineContextError(ValueError):
    """A machine-specific intent was received without a QR/machine identifier."""


@dataclass(frozen=True)
class OrchestrationResult:
    agent: str
    answer: str
    manual_evidence: list[dict[str, Any]] | None = None
    structured_data: dict[str, Any] | None = None


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


async def _iot_evidence(message: str, machine_id: str, user: AuthContext) -> dict[str, Any]:
    """Choose a bounded database operation instead of always loading five rows."""

    text = message.casefold()
    periods = _iso_periods(message)
    start_time, end_time = periods[0] if periods else (None, None)
    code_match = ALARM_CODE_PATTERN.search(message)
    alarm_code = code_match.group(0).upper() if code_match else None
    count_terms = ("how many", "number of", "count", "quante", "quanti", "conteggio")
    summary_terms = ("most frequent", "recurring", "repeated", "group", "frequency", "più frequ", "ricorrent")
    telemetry_terms = ("telemetr", "temperature", "energy", "uptime", "production", "temperatura", "energia", "produzion")
    statistic_terms = ("average", "mean", "minimum", "maximum", "total", "trend", "media", "minim", "massim", "totale", "andamento")

    if alarm_code and any(term in text for term in count_terms):
        return {"operation": "count_alarms", "result": await count_alarms(
            machine_id, user, start_time=start_time, end_time=end_time,
            alarm_code=alarm_code,
        )}
    if "alarm" in text or "allarm" in text:
        if any(term in text for term in summary_terms):
            return {"operation": "alarm_summary", "result": await alarm_summary(
                machine_id, user, start_time=start_time, end_time=end_time,
                alarm_code=alarm_code,
            )}
        return {"operation": "recent_alarms", "machine_id": machine_id, "alarms": await recent_alarms(
            machine_id, user, 20, start_time=start_time, end_time=end_time,
            alarm_code=alarm_code,
        )}
    if any(term in text for term in telemetry_terms) and any(term in text for term in statistic_terms):
        if len(periods) >= 2 and any(term in text for term in ("compare", "comparison", "confront")):
            return {"operation": "compare_telemetry_periods", "result": await compare_telemetry_periods(
                machine_id, user,
                first_start=periods[0][0], first_end=periods[0][1],
                second_start=periods[1][0], second_end=periods[1][1],
            )}
        return {"operation": "telemetry_summary", "result": await telemetry_summary(
            machine_id, user, start_time=start_time, end_time=end_time,
        )}
    return {
        "operation": "recent_operational_data",
        "machine_id": machine_id,
        "alarms": await recent_alarms(machine_id, user, 20, start_time=start_time, end_time=end_time),
        "telemetry": await telemetry(machine_id, user, 20, start_time=start_time, end_time=end_time),
    }


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


async def _evidence(intent: str, message: str, machine_id: str | None, user: AuthContext) -> Any:
    if intent == "iot":
        target = _require_machine(message, machine_id)
        return await _iot_evidence(message, target, user)
    if intent == "alarm_guidance":
        target = _require_machine(message, machine_id)
        code = ALARM_CODE_PATTERN.search(message)
        assert code is not None
        return await explain_alarm(target, code.group(0), user, 5)
    if intent == "service":
        target = _require_machine(message, machine_id)
        return {"machine_id": target, "maintenance_tickets": await maintenance_tickets(target, user, 10)}
    if intent == "maintenance_due":
        target = _require_machine(message, machine_id)
        return {"maintenance_observation": await observed_maintenance_plan(target, user)}
    if intent == "manuals":
        target = _require_machine(message, machine_id)
        return {"machine_id": target, "manual_evidence": await search_manual(target, message, user, 5)}
    if intent == "troubleshoot":
        target = _require_machine(message, machine_id)
        return await investigate(target, message, user, 5)
    if intent == "orders":
        return {"orders": await orders(user, 10), "quotes": await quotes(user, 10)}
    return None


def _manual_reference(chunk: dict[str, Any]) -> str:
    """Format one local-only manual citation for a chat response."""

    return f"{chunk['file']}, p. {chunk['page']}, sezione {chunk['section']}"


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


def _local_alarm_guidance_answer(evidence: dict[str, Any]) -> str:
    """Explain the mnemonic and point to local manual evidence without an LLM."""

    events = evidence["recent_events"]
    event_summary = (
        "; ".join(
            f"{event['severity']} / {event['alarm_status']} ({event['timestamp'].isoformat()})"
            for event in events
        )
        if events
        else "Operational event history is unavailable for your role, or no matching events were found."
    )
    manual_answer = _local_manual_answer({"manual_evidence": evidence["manual_evidence"]})
    return (
        f"{evidence['alarm_code']} means: {evidence['meaning']}. "
        f"Recent events: {event_summary}\n\n{manual_answer}"
    )


def _local_maintenance_due_answer(evidence: dict[str, Any]) -> str:
    """Report documented thresholds against the actual telemetry coverage only."""

    observation = evidence["maintenance_observation"]
    reached = observation["reached_threshold_hours"]
    reached_text = ", ".join(f"{threshold} h" for threshold in reached) if reached else "none"
    next_threshold = observation["next_threshold_hours"]
    next_text = f"{next_threshold} h" if next_threshold is not None else "none documented"
    first_snapshot = observation["first_snapshot"]
    last_snapshot = observation["last_snapshot"]
    period = (
        f"{first_snapshot.isoformat()} to {last_snapshot.isoformat()}"
        if first_snapshot is not None and last_snapshot is not None
        else "the available telemetry window"
    )
    return (
        f"For {observation['machine_id']}, telemetry from {period} contains "
        f"{observation['observed_productive_hours']} observed productive hours. "
        f"Documented thresholds reached in this window: {reached_text}. "
        f"Next documented threshold: {next_text}.\n\n"
        f"{observation['scope_note']}"
    )


async def handle_chat(
    message: str,
    user: AuthContext,
    machine_id: str | None = None,
) -> OrchestrationResult:
    """Route a chat message, collect authorised evidence, and compose an answer."""

    intent = classify_intent(message)
    if intent == "general":
        return OrchestrationResult("general", await generate_chat_reply(message))

    evidence = await _evidence(intent, message, machine_id, user)
    # The course manuals are restricted local material. Their text can be shown
    # to an authorised user, but is never included in a request to an external
    # LLM provider.
    if intent == "manuals":
        return OrchestrationResult(
            "manuals",
            _local_manual_answer(evidence),
            manual_evidence=evidence["manual_evidence"],
        )
    if intent == "troubleshoot":
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
        return OrchestrationResult(
            "alarm_guidance",
            _local_alarm_guidance_answer(evidence),
            manual_evidence=evidence["manual_evidence"],
            structured_data={
                "machine_id": evidence["machine_id"],
                "alarms": evidence["recent_events"],
            },
        )
    if intent == "maintenance_due":
        return OrchestrationResult(
            "maintenance_due",
            _local_maintenance_due_answer(evidence),
            structured_data={"maintenance_observation": evidence["maintenance_observation"]},
        )

    prompt = (
        f"User question: {message}\n\n"
        "Use only the following evidence retrieved by authorised backend tools. "
        "If it is empty, say that no matching records were found. Do not invent values. "
        "Answer only in English and mention the relevant IDs and statuses. "
        f"Use {BUSINESS_TODAY.isoformat()} as today's date when interpreting "
        "quote expiry, open items, or overdue work.\n\n"
        f"Evidence ({intent} agent):\n{json.dumps(evidence, default=str, ensure_ascii=False)}"
    )
    system_prompt = (
        "You are the AROL Customer Platform assistant. "
        "The backend has already enforced authentication, company scope, and role permissions. "
        "Summarise only the supplied evidence; never reveal or infer data outside it."
    )
    return OrchestrationResult(
        intent,
        await generate_chat_reply(prompt, system_prompt=system_prompt),
        structured_data=evidence,
    )
