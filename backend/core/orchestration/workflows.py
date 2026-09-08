"""Named evidence workflows reused by chat and direct API endpoints."""

from __future__ import annotations

from core.alarm_codes import alarm_meaning, normalise_alarm_code
from core.contracts import AgentRequest, OrchestrationPlan
from core.maintenance_observation import maintenance_observation
from core.orchestration.models import EvidenceBundle

def maintenance_observation_plan() -> OrchestrationPlan:
    """Collect independent IoT and Manuals evidence for a maintenance question."""

    return OrchestrationPlan(requests=[
        AgentRequest(agent="iot", operation="observed_productive_hours"),
        AgentRequest(agent="manuals", operation="maintenance_requirements"),
    ])


def correlate_maintenance_observation(bundle: EvidenceBundle) -> EvidenceBundle:
    """Add a cautious orchestration conclusion to independent agent evidence."""

    productive_hours = next(
        (item.evidence for item in bundle.results
         if item.agent == "iot" and item.operation == "observed_productive_hours"),
        None,
    )
    manual_requirements = next(
        (item.evidence for item in bundle.results
         if item.agent == "manuals" and item.operation == "maintenance_requirements"),
        None,
    )
    if productive_hours is None or manual_requirements is None:
        raise RuntimeError("Maintenance correlation requires IoT and Manuals evidence.")

    observation = maintenance_observation(
        productive_hours["machine_id"],
        productive_hours,
        manual_requirements["requirements"],
    )
    correlation_evidence = {"maintenance_observation": observation}
    return EvidenceBundle(
        bundle.results,
        [*bundle.composer_evidence, {
            "agent": "orchestrator",
            "operation": "correlate_maintenance_observation",
            "evidence": correlation_evidence,
            "sources": [],
            "warnings": [],
        }],
        correlation_evidence,
    )


def alarm_guidance_plan(
    alarm_code: str,
    limit: int,
    *,
    include_recent_events: bool,
) -> OrchestrationPlan:
    """Build atomic alarm-code, optional event, and manual evidence requests."""

    normalized_code = normalise_alarm_code(alarm_code)
    requests = [
        AgentRequest(
            agent="iot",
            operation="alarm_meaning",
            parameters={"alarm_code": normalized_code},
        ),
    ]
    if include_recent_events:
        requests.append(
            AgentRequest(
                agent="iot",
                operation="recent_alarms",
                parameters={"alarm_code": normalized_code, "limit": limit},
            )
        )
    requests.append(
        AgentRequest(
            agent="manuals",
            operation="search",
            parameters={
                "query": (
                    f"{normalized_code} {alarm_meaning(normalized_code)} "
                    "cause remedy troubleshooting"
                ),
                "limit": limit,
            },
        )
    )
    return OrchestrationPlan(requests=requests)

