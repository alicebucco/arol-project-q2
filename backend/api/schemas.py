"""Pydantic contracts for the public HTTP API."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core.contracts import ConversationTurn


class ChatRequest(BaseModel):
    """One chat message with bounded, non-persistent conversational context."""

    message: str = Field(min_length=1, max_length=4_000)
    machine_id: str | None = Field(default=None, max_length=100)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def valid_history(self) -> "ChatRequest":
        if sum(len(turn.content) for turn in self.history) > 12_000:
            raise ValueError("The chat history is too long.")
        if any(
            turn.role != ("user" if index % 2 == 0 else "assistant")
            for index, turn in enumerate(self.history)
        ):
            raise ValueError("Chat history must alternate user and assistant turns.")
        if self.history and self.history[-1].role != "assistant":
            raise ValueError("Chat history must end with an assistant turn.")
        return self

class MachineContext(BaseModel):
    """Machine context resolved from a QR code value."""

    machine_id: str
    serial_number: str
    company_id: str
    company_name: str
    model_id: str
    model_code: str
    model_description: str | None = None
    plant_location: str | None = None
    delivery_date: str | None = None
    plc_family: str | None = None
    software_version: str | None = None
    configuration_profile: str | None = None
    operational_context: str

class MachineSummary(BaseModel):
    machine_id: str
    serial_number: str
    model_code: str
    model_description: str | None = None
    plant_location: str | None = None
    configuration_profile: str | None = None

class SessionUser(BaseModel):
    user_id: str
    company_id: str
    visibility: str

class UserProfile(SessionUser):
    first_name: str
    last_name: str
    email: str
    job_title: str
    company_name: str
    country: str
    city: str
    sector: str
    currency: str
    locale: str

class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)

class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: SessionUser

class AlarmRecord(BaseModel):
    alarm_id: str
    timestamp: str
    alarm_code: str
    severity: str
    alarm_status: str

class TelemetryRecord(BaseModel):
    timestamp: str
    operational_status: str
    production_rate_bph: float
    uptime_percentage: float
    alarm_count: int
    temperature_c: float | None = None
    energy_kwh: float | None = None
    health_note: str | None = None
    production_assessment: "ProductionAssessment | None" = None

class ProductionAssessment(BaseModel):
    """Machine-specific production reference attached to a telemetry snapshot."""

    nominal_production_rate_bph: float | None = None
    production_vs_nominal_percent: float | None = None
    status: Literal[
        "within_expected_range",
        "below_nominal_reference",
        "above_nominal_reference",
        "not_assessed",
    ]
    reason: str

class MaintenanceTicketRecord(BaseModel):
    ticket_id: str
    alarm_id: str | None = None
    ticket_type: str
    ticket_status: str
    priority: str
    created_date: str
    owner_role: str

class MaintenanceObservation(BaseModel):
    """Maintenance thresholds compared with the available telemetry window."""

    machine_id: str
    observed_productive_hours: float
    first_snapshot: str | None = None
    last_snapshot: str | None = None
    snapshot_count: int
    documented_threshold_hours: list[int]
    reached_threshold_hours: list[int]
    next_threshold_hours: int | None = None
    scope_note: str

class OrderRecord(BaseModel):
    order_id: str
    quote_id: str
    order_status: str
    shipment_status: str
    currency: str | None = None
    order_date: date | None = None

class OrderItem(BaseModel):
    quote_line_id: str
    machine_id: str | None = None
    description: str | None = None
    price: float

class FulfillmentLine(BaseModel):
    order_line_id: str
    fulfillment_status: str

class ApprovedOrderRevision(BaseModel):
    revision_number: int
    revision_status: str
    discount_rate: float | None = None

class OrderDetail(OrderRecord):
    currency: str | None = None
    approved_revision: ApprovedOrderRevision | None = None
    items: list[OrderItem]
    fulfillment: list[FulfillmentLine]

class QuoteRecord(BaseModel):
    currency: str | None = None
    created_at: date | None = None
    quote_id: str
    valid_until: str | None = None
    validity_status: Literal["Valid", "Expired", "Unknown"]
    revision_number: int | None = None
    revision_status: str | None = None
    discount_rate: float | None = None
    line_total: float

class QuoteLineDetail(BaseModel):
    quote_line_id: str
    machine_id: str | None = None
    description: str | None = None
    price: float

class QuoteRevisionDetail(BaseModel):
    quote_revision_id: str
    revision_number: int
    revision_status: str
    discount_rate: float | None = None
    issued_at: str | None = None
    change_summary: str | None = None
    line_total: float
    lines: list[QuoteLineDetail]

class QuoteLineChange(BaseModel):
    previous_lines: list[QuoteLineDetail] = Field(default_factory=list)
    current_lines: list[QuoteLineDetail] = Field(default_factory=list)
    change: Literal["added", "removed", "price_changed", "ambiguous"]
    machine_id: str | None = None
    description: str | None = None
    previous_price: float | None = None
    current_price: float | None = None

class QuoteHistory(BaseModel):
    quote_id: str
    valid_until: str | None = None
    validity_status: Literal["Valid", "Expired", "Unknown"]
    currency: str | None = None
    created_at: str | None = None
    description: str | None = None
    revisions: list[QuoteRevisionDetail]
    latest_comparison: list[QuoteLineChange]
    comparison_basis: str | None = None

class ManualCitation(BaseModel):
    source: Literal["manual"]
    chunk_id: str | None = None
    file: str
    page: int
    section: str

class ManualSearchResult(BaseModel):
    citation: ManualCitation
    excerpt: str
    title: str
    highlights: list[str]
    relevance: float
    similarity: float
    similarity_threshold_met: bool = False
    alarm_code_match: Literal["not_requested", "exact_in_passage", "semantic_only"] = "not_requested"
    excerpt_is_complete_chunk: bool = False
    section_category: str | None = None
    section_category_is_inferred: bool = True
    documented_section_title: str | None = None

class AlarmGuidance(BaseModel):
    machine_id: str
    alarm_code: str
    meaning: str
    recent_events: list[AlarmRecord]
    manual_evidence: list[ManualSearchResult]

class ChatResponse(BaseModel):
    """Chat output, with structured local manual sources when available."""

    answer: str
    agent: list[Literal["iot", "manuals", "service", "orders"]] | None = None
    sources: list[ManualSearchResult] = Field(default_factory=list)
    data: dict[str, Any] | None = None
