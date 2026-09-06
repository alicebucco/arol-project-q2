"""Convert authorised agent data into the orchestration evidence contract.

Agents return domain data only.  This module is the single boundary that
creates ``AgentResult`` instances for the registry and the composer.
"""

from __future__ import annotations

from typing import Any

from core.contracts import AgentName, AgentResult, EvidenceSource


def agent_result(
    agent: AgentName,
    operation: str,
    evidence: dict[str, Any],
    *,
    structured_data: dict[str, Any] | None = None,
    sources: list[EvidenceSource] | None = None,
    warnings: list[str] | None = None,
) -> AgentResult:
    """Build a validated result without making agents depend on core contracts."""

    return AgentResult(
        agent=agent,
        operation=operation,
        evidence=evidence,
        structured_data=structured_data,
        sources=sources or [],
        warnings=warnings or [],
    )


def manual_search_result(machine_id: str, matches: list[dict[str, Any]]) -> AgentResult:
    """Expose bounded manual citations while keeping raw PDF chunks local."""

    public_matches = [{key: value for key, value in match.items() if key != "content"} for match in matches]
    sources = [
        EvidenceSource(
            source_id=f"manual:{match['file']}:{match['page']}",
            source_type="manual",
            citation={
                "file": match["file"],
                "page": match["page"],
                "section": match["section"],
                "title": match.get("title"),
                "relevance": match.get("relevance"),
            },
            excerpt=match.get("excerpt"),
        )
        for match in public_matches
    ]
    evidence = {
        "machine_id": machine_id,
        "match_count": len(sources),
        "manual_evidence": public_matches,
    }
    return agent_result(
        "manuals",
        "search",
        evidence,
        structured_data={"machine_id": machine_id, "manual_evidence": public_matches},
        sources=sources,
    )
