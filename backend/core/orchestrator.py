"""Intent routing and response composition for the conversational API."""

import json
import re
from dataclasses import dataclass
from typing import Any

from agents.iot import recent_alarms, telemetry
from agents.manuals import ManualsUnavailableError, search as search_manual
from agents.orders import orders, quotes
from agents.service import maintenance_tickets
from agents.troubleshoot import investigate
from core.auth import AuthContext
from core.data_access import MachineNotFoundError
from core.llm import generate_chat_reply


class MissingMachineContextError(ValueError):
    """A machine-specific intent was received without a QR/machine identifier."""


@dataclass(frozen=True)
class OrchestrationResult:
    agent: str
    answer: str


MACHINE_PATTERN = re.compile(r"\bMCH-[A-Z0-9-]+\b", re.IGNORECASE)


def classify_intent(message: str) -> str:
    """Route using explicit keywords before invoking the LLM."""

    text = message.casefold()
    if any(word in text for word in ("perché", "perche", "diagnos", "causa", "problema", "troubleshoot")):
        return "troubleshoot"
    if any(word in text for word in ("manuale", "istruzioni", "configurazione", "sicurezza")):
        return "manuals"
    if any(word in text for word in ("allarm", "telemetr", "produzion", "uptime", "temperatura", "stato operativo")):
        return "iot"
    if any(word in text for word in ("manutenz", "ticket", "intervento", "service")):
        return "service"
    if any(
        word in text
        for word in (
            "ordine",
            "ordini",
            "preventiv",
            "quotazione",
            "prezzo",
            "sconto",
            "spedizion",
            "costo",
            "costa",
            "costat",
            "fattura",
            "acquist",
        )
    ):
        return "orders"
    return "general"


def _machine_id(message: str, machine_id: str | None) -> str | None:
    if machine_id and machine_id.strip():
        return machine_id.strip()
    match = MACHINE_PATTERN.search(message)
    return match.group(0).upper() if match else None


def _require_machine(message: str, machine_id: str | None) -> str:
    resolved = _machine_id(message, machine_id)
    if resolved is None:
        raise MissingMachineContextError(
            "Indica la macchina (ad esempio MCH-0001) oppure apri la chat dopo aver scansionato il QR."
        )
    return resolved


async def _evidence(intent: str, message: str, machine_id: str | None, user: AuthContext) -> Any:
    if intent == "iot":
        target = _require_machine(message, machine_id)
        return {"machine_id": target, "alarms": await recent_alarms(target, user, 5), "telemetry": await telemetry(target, user, 5)}
    if intent == "service":
        target = _require_machine(message, machine_id)
        return {"machine_id": target, "maintenance_tickets": await maintenance_tickets(target, user, 10)}
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
        return "Non ho trovato passaggi pertinenti nel manuale di questa macchina."

    excerpts = "\n\n".join(
        f"[{_manual_reference(chunk)}]\n{chunk['content']}" for chunk in chunks
    )
    return (
        "Ho trovato i seguenti estratti nel manuale della macchina. "
        "Verifica la procedura completa e le avvertenze di sicurezza indicate.\n\n"
        f"{excerpts}"
    )


def _local_troubleshoot_answer(evidence: dict[str, Any]) -> str:
    """Return diagnostic evidence locally, never exposing manual text to the LLM."""

    alarms = evidence["alarms"]
    tickets = evidence["maintenance_tickets"]
    alarm_summary = (
        "; ".join(
            f"{alarm['alarm_code']} ({alarm['severity']}, {alarm['alarm_status']})"
            for alarm in alarms
        )
        if alarms
        else "nessun allarme recente"
    )
    ticket_summary = (
        "; ".join(
            f"{ticket['ticket_id']} ({ticket['ticket_status']}, priorità {ticket['priority']})"
            for ticket in tickets
        )
        if tickets
        else "nessun ticket recente"
    )
    manual_answer = _local_manual_answer(
        {"manual_evidence": evidence["manual_evidence"]}
    )
    return (
        f"Dati raccolti per {evidence['machine_id']}: {alarm_summary}. "
        f"Ticket di manutenzione: {ticket_summary}.\n\n"
        f"{manual_answer}"
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
        return OrchestrationResult("manuals", _local_manual_answer(evidence))
    if intent == "troubleshoot":
        return OrchestrationResult("troubleshoot", _local_troubleshoot_answer(evidence))

    prompt = (
        f"User question: {message}\n\n"
        "Use only the following evidence retrieved by authorised backend tools. "
        "If it is empty, say that no matching records were found. Do not invent values. "
        "Answer in Italian and mention the relevant IDs/statuses.\n\n"
        f"Evidence ({intent} agent):\n{json.dumps(evidence, default=str, ensure_ascii=False)}"
    )
    system_prompt = (
        "You are the AROL Customer Platform assistant. "
        "The backend has already enforced authentication, company scope, and role permissions. "
        "Summarise only the supplied evidence; never reveal or infer data outside it."
    )
    return OrchestrationResult(intent, await generate_chat_reply(prompt, system_prompt=system_prompt))
