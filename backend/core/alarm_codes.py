"""Deterministic validation and display names for dataset alarm codes."""

from __future__ import annotations

import re


ALARM_CODE_PATTERN = re.compile(r"^(AL\d{3})_([A-Z0-9_]+)$")


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
