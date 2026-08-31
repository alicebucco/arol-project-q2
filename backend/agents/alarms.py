"""Alarm-code guidance backed by the authorised machine manual."""

from __future__ import annotations

import re
from typing import Any

from agents.manuals import search as search_manual
from core.auth import AuthContext
from core.data_access import authorize_machine, get_recent_alarms_for_code


ALARM_CODE_PATTERN = re.compile(r"^(AL\d{3})_([A-Z0-9_]+)$")


def normalise_alarm_code(alarm_code: str) -> str:
    """Validate the dataset alarm-code convention before searching for it."""

    normalized = alarm_code.strip().upper()
    if not ALARM_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("An alarm code must have the form ALnnn_MNEMONIC.")
    return normalized


def alarm_meaning(alarm_code: str) -> str:
    """Use the dataset mnemonic as a transparent human-readable description."""

    match = ALARM_CODE_PATTERN.fullmatch(normalise_alarm_code(alarm_code))
    assert match is not None
    return match.group(2).replace("_", " ").lower().capitalize()


async def explain(
    machine_id: str,
    alarm_code: str,
    user: AuthContext,
    limit: int,
) -> dict[str, Any]:
    """Return local manual guidance, plus recent events when operations are visible."""

    normalized_code = normalise_alarm_code(alarm_code)
    await authorize_machine(machine_id, user, domain="manuals")
    manual_evidence = await search_manual(
        machine_id,
        f"{normalized_code} {alarm_meaning(normalized_code)} cause remedy troubleshooting",
        user,
        limit,
    )

    recent_events: list[dict[str, Any]] = []
    if user.visibility in {"full", "technician"}:
        # The machine has already been tenant-authorised above; this query adds
        # operational context without granting it to commercial-only users.
        recent_events = await get_recent_alarms_for_code(machine_id, normalized_code, limit)

    return {
        "machine_id": machine_id,
        "alarm_code": normalized_code,
        "meaning": alarm_meaning(normalized_code),
        "recent_events": recent_events,
        "manual_evidence": manual_evidence,
    }
