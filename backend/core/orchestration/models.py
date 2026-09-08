"""Value objects exchanged by orchestration components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.contracts import AgentName, AgentResult

@dataclass(frozen=True)
class OrchestrationResult:
    agent: list[AgentName] | None
    answer: str
    manual_evidence: list[dict[str, Any]] | None = None
    structured_data: dict[str, Any] | None = None


@dataclass(frozen=True)
class EvidenceBundle:
    """Agent results kept separate for composition and for the existing UI."""

    results: list[AgentResult]
    composer_evidence: list[dict[str, Any]]
    structured_data: dict[str, Any]
