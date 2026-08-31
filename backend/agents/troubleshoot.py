"""Troubleshoot Agent: compose operational and manual evidence for one machine."""

from typing import Any

from core.auth import AuthContext
from core.data_access import authorize_machine, get_repeated_alarm_patterns
from agents.alarms import alarm_meaning
from agents.iot import recent_alarms, telemetry
from agents.manuals import search as search_manual
from agents.service import maintenance_tickets


async def investigate(
    machine_id: str,
    query: str,
    user: AuthContext,
    limit: int,
) -> dict[str, Any]:
    """Collect cited evidence without transmitting restricted manuals externally."""
    await authorize_machine(machine_id, user, domain="operational")

    alarms = await recent_alarms(machine_id, user, limit)
    repeated_alarm_patterns = await get_repeated_alarm_patterns(machine_id, limit)
    snapshots = await telemetry(machine_id, user, limit)
    tickets = await maintenance_tickets(machine_id, user, limit)
    codes = [pattern["alarm_code"] for pattern in repeated_alarm_patterns]
    if not codes:
        codes = list(dict.fromkeys(alarm["alarm_code"] for alarm in alarms))
    manual_query = " ".join(
        f"{code} {alarm_meaning(code)} cause remedy troubleshooting"
        for code in codes[:3]
    ) or query
    manual_evidence = await search_manual(machine_id, manual_query, user, limit)

    return {
        "machine_id": machine_id,
        "query": query,
        "summary": (
            f"Found {len(repeated_alarm_patterns)} repeated alarm condition(s), {len(alarms)} recent alarms, {len(tickets)} maintenance tickets, "
            f"{len(snapshots)} telemetry snapshots, and {len(manual_evidence)} cited manual chunks. "
            "Review the evidence before determining a cause or remedy."
        ),
        "alarms": alarms,
        "repeated_alarm_patterns": repeated_alarm_patterns,
        "telemetry": snapshots,
        "maintenance_tickets": tickets,
        "manual_evidence": manual_evidence,
    }
