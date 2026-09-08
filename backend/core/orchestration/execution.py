"""Trusted execution of registered evidence plans."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from core.auth import AuthContext
from core.contracts import OrchestrationPlan
from core.operations.catalogue import OPERATION_REGISTRY
from core.operations.registry import OperationContext
from core.orchestration.models import EvidenceBundle

MACHINE_PATTERN = re.compile(r"\bMCH-[A-Z0-9-]+\b", re.IGNORECASE)

class MissingMachineContextError(ValueError):
    """A machine-specific intent was received without a QR/machine identifier."""


def resolve_machine_id(message: str, machine_id: str | None) -> str | None:
    if machine_id and machine_id.strip():
        return machine_id.strip()
    match = MACHINE_PATTERN.search(message)
    return match.group(0).upper() if match else None


def require_machine(message: str, machine_id: str | None) -> str:
    resolved = resolve_machine_id(message, machine_id)
    if resolved is None:
        raise MissingMachineContextError(
            "Select a machine first, or include its ID (for example, MCH-0001) in your question."
        )
    return resolved


async def execute_plan(
    plan: OrchestrationPlan,
    message: str,
    machine_id: str | None,
    user: AuthContext,
) -> EvidenceBundle:
    """Execute only allow-listed operations and retain each result boundary."""

    target = (
        require_machine(message, machine_id)
        if OPERATION_REGISTRY.plan_requires_machine_context(plan.requests)
        else None
    )
    context = OperationContext(user=user, machine_id=target)
    # Every request in the current plan contract is independent: no request can
    # consume another request's output. ``gather`` starts their read-only
    # evidence retrieval concurrently while retaining the planner's order in
    # the resulting list for deterministic composition and frontend data.
    results = await asyncio.gather(
        *(OPERATION_REGISTRY.execute(request, context) for request in plan.requests)
    )

    structured_data: dict[str, Any] = {}
    composer_evidence: list[dict[str, Any]] = []
    for result in results:
        if result.structured_data:
            structured_data.update(result.structured_data)
        composer_evidence.append(
            {
                "agent": result.agent,
                "operation": result.operation,
                "evidence": result.evidence,
                "sources": [source.model_dump() for source in result.sources],
                "warnings": result.warnings,
            }
        )
    return EvidenceBundle(results, composer_evidence, structured_data)
