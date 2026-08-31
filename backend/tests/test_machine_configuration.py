from core.machine_configuration import nominal_production_rate_bph, production_assessment


def _snapshot(status: str, rate: float) -> dict[str, object]:
    return {"operational_status": status, "production_rate_bph": rate}


def test_extracts_nominal_rate_from_the_machine_profile() -> None:
    assert nominal_production_rate_bph("Twin chute / 20 heads / 40,000 bph / 400V-60Hz") == 40000
    assert nominal_production_rate_bph("No rate supplied") is None


def test_compares_running_telemetry_with_the_specific_machine_profile() -> None:
    within_range = production_assessment(_snapshot("Running", 38000), "Twin chute / 40000 bph")
    below_reference = production_assessment(_snapshot("Running", 28000), "Twin chute / 40000 bph")

    assert within_range["status"] == "within_expected_range"
    assert within_range["production_vs_nominal_percent"] == 95.0
    assert below_reference["status"] == "below_nominal_reference"


def test_does_not_treat_zero_production_outside_running_as_a_fault() -> None:
    assessment = production_assessment(_snapshot("Maintenance", 0), "Twin chute / 40000 bph")

    assert assessment["status"] == "not_assessed"
    assert assessment["production_vs_nominal_percent"] == 0.0
    assert "not evaluated outside Running" in assessment["reason"]
