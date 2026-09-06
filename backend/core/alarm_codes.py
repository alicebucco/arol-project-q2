"""Deterministic validation and display names for dataset alarm codes."""

from __future__ import annotations

import re


ALARM_CODE_PREFIX_EXPRESSION = r"AL\d{3}"
ALARM_CODE_MNEMONIC_EXPRESSION = r"[A-Z0-9_]+"
ALARM_CODE_EXPRESSION = (
    f"{ALARM_CODE_PREFIX_EXPRESSION}_{ALARM_CODE_MNEMONIC_EXPRESSION}"
)
ALARM_CODE_PATTERN = re.compile(
    rf"^({ALARM_CODE_PREFIX_EXPRESSION})_({ALARM_CODE_MNEMONIC_EXPRESSION})$"
)
ALARM_CODE_IN_TEXT_PATTERN = re.compile(rf"\b{ALARM_CODE_EXPRESSION}\b", re.IGNORECASE)


def normalise_alarm_code(alarm_code: str) -> str:
    """Validate the dataset convention before using an alarm code as evidence."""

    normalized = alarm_code.strip().upper()
    if not ALARM_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("An alarm code must have the form ALnnn_MNEMONIC.")
    return normalized


def alarm_meaning(alarm_code: str) -> str:
    """Turn the dataset mnemonic into its deterministic display name."""

    match = ALARM_CODE_PATTERN.fullmatch(normalise_alarm_code(alarm_code))
    assert match is not None
    return match.group(2).replace("_", " ").lower().capitalize()
