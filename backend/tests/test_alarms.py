import asyncio
from unittest.mock import AsyncMock

import pytest

from core.auth import AuthContext
from core.alarm_codes import alarm_meaning, normalise_alarm_code
import core.orchestrator as orchestrator


def test_alarm_code_is_validated_and_its_mnemonic_is_readable() -> None:
    assert normalise_alarm_code(" al017_low_air_pressure ") == "AL017_LOW_AIR_PRESSURE"
    assert alarm_meaning("AL017_LOW_AIR_PRESSURE") == "Low air pressure"
    with pytest.raises(ValueError, match="ALnnn_MNEMONIC"):
        normalise_alarm_code("low air pressure")


def test_commercial_user_receives_manual_guidance_without_operational_events(monkeypatch) -> None:
    monkeypatch.setattr(orchestrator, "authorize_machine", AsyncMock())
    monkeypatch.setattr(orchestrator, "search_manual", AsyncMock(return_value=[{"page": 97}]))
    recent_events = AsyncMock(return_value=[{"alarm_id": "ALM-1"}])
    monkeypatch.setattr(orchestrator, "get_recent_alarms_for_code", recent_events)

    report = asyncio.run(
        orchestrator.alarm_guidance_evidence(
            "MCH-0001",
            "AL017_LOW_AIR_PRESSURE",
            AuthContext("USR-1", "CMP-001", "commercial"),
            5,
        )
    )

    assert report["meaning"] == "Low air pressure"
    assert report["manual_evidence"] == [{"page": 97}]
    assert report["recent_events"] == []
    recent_events.assert_not_awaited()
