import asyncio
from unittest.mock import AsyncMock

from agents import iot
from core.auth import AuthContext


def test_iot_telemetry_uses_machine_specific_configuration(monkeypatch) -> None:
    monkeypatch.setattr(iot, "authorize_machine", AsyncMock())
    monkeypatch.setattr(iot, "get_machine_configuration_profile", AsyncMock(return_value="6 heads / 10000 bph / 480V"))
    monkeypatch.setattr(
        iot,
        "get_telemetry_snapshots",
        AsyncMock(return_value=[{"operational_status": "Running", "production_rate_bph": 8500}]),
    )

    rows = asyncio.run(iot.telemetry("MCH-0002", AuthContext("USR-1", "CMP-1", "full"), 5))

    assert rows[0]["production_assessment"] == {
        "nominal_production_rate_bph": 10000.0,
        "production_vs_nominal_percent": 85.0,
        "status": "below_nominal_reference",
        "reason": "Production is more than 10% below this machine's configured nominal rate.",
    }
