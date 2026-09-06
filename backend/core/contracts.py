"""Typed contracts for LLM plans and evidence returned by backend agents.

These models are deliberately independent of database records and FastAPI
response models.  They form the boundary between the future LLM planner, the
authorised agent dispatcher, and the LLM composer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AgentName = Literal["iot", "manuals", "service", "orders"]


class _StrictContract(BaseModel):
    """Reject fields that have not been explicitly approved by the backend."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AgentRequest(_StrictContract):
    """One allow-listable operation requested by an orchestration plan.

    ``parameters`` remains a generic object at this layer.  The operation
    registry introduced next validates it against the schema for the selected
    agent operation before anything is executed.
    """

    agent: AgentName
    operation: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    parameters: dict[str, Any] = Field(default_factory=dict)


class OrchestrationPlan(_StrictContract):
    """Validated, bounded work proposed for one chat question.

    The model can request several independent evidence operations, but it can
    neither select security scope nor execute arbitrary code, SQL, or tools.
    """

    requests: list[AgentRequest] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def bounded_agent_count(self) -> "OrchestrationPlan":
        if len({request.agent for request in self.requests}) > 4:
            raise ValueError("An orchestration plan may involve at most four agents.")
        return self


class PlannerDecision(_StrictContract):
    """The planner's top-level decision before any evidence is retrieved.

    A plan is meaningful only for ``retrieve_evidence``. General questions
    need no backend retrieval. Trusted context, such as a selected machine,
    is enforced by the backend after the decision is made.
    """

    action: Literal["retrieve_evidence", "answer_without_evidence"]
    plan: OrchestrationPlan | None = None

    @model_validator(mode="after")
    def valid_decision_shape(self) -> "PlannerDecision":
        if self.action == "retrieve_evidence":
            if self.plan is None:
                raise ValueError("Evidence retrieval requires a plan.")
        elif self.plan is not None:
            raise ValueError("An answer without evidence cannot include a plan.")
        return self


class EvidenceSource(_StrictContract):
    """A stable citation or record reference accompanying agent evidence."""

    source_id: str = Field(min_length=1, max_length=200)
    source_type: Literal["manual", "operational", "service", "commercial"]
    citation: dict[str, Any] = Field(default_factory=dict)
    excerpt: str | None = Field(default=None, max_length=2_000)


class AgentResult(_StrictContract):
    """Evidence produced by one authorised agent operation.

    ``evidence`` is for the composer; ``structured_data`` is reserved for the
    existing frontend tables.  They are intentionally separate so the LLM does
    not determine the UI data contract.
    """

    agent: AgentName
    operation: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    evidence: dict[str, Any] = Field(default_factory=dict)
    sources: list[EvidenceSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structured_data: dict[str, Any] | None = None
