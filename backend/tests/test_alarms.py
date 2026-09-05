import asyncio
from unittest.mock import AsyncMock

import pytest

from core.auth import AuthContext
from core.alarm_codes import alarm_meaning, normalise_alarm_code
from core.contracts import AgentResult
import core.orchestrator as orchestrator


def test_alarm_code_is_validated_and_its_mnemonic_is_readable() -> None:
    assert normalise_alarm_code(" al017_low_air_pressure ") == "AL017_LOW_AIR_PRESSURE"
    assert alarm_meaning("AL017_LOW_AIR_PRESSURE") == "Low air pressure"
    with pytest.raises(ValueError, match="ALnnn_MNEMONIC"):
        normalise_alarm_code("low air pressure")


def test_commercial_user_receives_manual_guidance_without_operational_events(monkeypatch) -> None:
    async def fake_execute(*_args, **_kwargs) -> orchestrator.EvidenceBundle:
        return orchestrator.EvidenceBundle(
            [
                AgentResult(
                    agent="iot",
                    operation="alarm_guidance_context",
                    evidence={
                        "machine_id": "MCH-0001",
                        "alarm_code": "AL017_LOW_AIR_PRESSURE",
                        "meaning": "Low air pressure",
                        "recent_events": [],
                    },
                    warnings=["Operational event history is unavailable for the current role."],
                ),
                AgentResult(
                    agent="manuals",
                    operation="search",
                    evidence={"machine_id": "MCH-0001", "manual_evidence": [{"page": 97}]},
                ),
            ],
            [],
            {"machine_id": "MCH-0001", "alarms": []},
        )

    execute = AsyncMock(side_effect=fake_execute)
    monkeypatch.setattr(orchestrator, "_execute_plan", execute)

    bundle = asyncio.run(
        orchestrator.retrieve_alarm_guidance_evidence(
            "MCH-0001",
            "AL017_LOW_AIR_PRESSURE",
            AuthContext("USR-1", "CMP-001", "commercial"),
            5,
        )
    )

    assert bundle.results[0].evidence["meaning"] == "Low air pressure"
    assert bundle.results[1].evidence["manual_evidence"] == [{"page": 97}]
    assert bundle.results[0].evidence["recent_events"] == []
    assert execute.await_args.args[0].requests[0].operation == "alarm_guidance_context"
