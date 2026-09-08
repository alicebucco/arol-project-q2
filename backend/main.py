"""FastAPI entry point for the AROL Customer Platform backend."""

from datetime import date, datetime
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from core.auth import (
    AuthContext,
    authenticate_password,
    create_access_token,
    ensure_company_access,
    ensure_visibility,
    get_current_user,
)
from core.config import get_settings
from core.contracts import ConversationTurn
from core.db import check_connection, connection
from core.data_access import (
    MachineUnavailableError,
    MachineNotFoundError,
    TicketNotFoundError,
    OrderNotFoundError,
    QuoteNotFoundError,
    get_company_machines,
    get_user_profile,
)
from core.llm import LlmNotConfiguredError, LlmRequestError, generate_chat_reply
from core.orchestrator import (
    MissingMachineContextError,
    handle_chat,
    retrieve_alarm_guidance_evidence,
    retrieve_maintenance_observation,
)
from agents.iot import (
    alarm_summary,
    compare_telemetry_periods,
    count_alarms,
    recent_alarms,
    telemetry,
    telemetry_summary,
)
from agents.service import maintenance_tickets, search_tickets, ticket_detail
from agents.orders import order_detail, quote_history, search_orders, search_quotes
from agents.manuals import ManualsUnavailableError, can_open_file, search as search_manual


MANUALS_DIRECTORY = Path("/data/manuals")


app = FastAPI(title="AROL Customer Platform API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # Vite may be opened through either localhost or 127.0.0.1 during local
    # development.  Browsers treat them as distinct origins.
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Returned-Count", "X-Is-Truncated", "X-Limit"],
)


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


def manual_search_result(row: dict[str, object]) -> ManualSearchResult:
    """Map an internal local manual result to the public API contract."""
    return ManualSearchResult(
        citation=ManualCitation(
            source=row["source"],  # type: ignore[arg-type]
            chunk_id=row.get("chunk_id"),  # type: ignore[arg-type]
            file=row["file"],  # type: ignore[arg-type]
            page=row["page"],  # type: ignore[arg-type]
            section=row["section"],  # type: ignore[arg-type]
        ),
        excerpt=row["excerpt"],  # type: ignore[arg-type]
        title=row["title"],  # type: ignore[arg-type]
        highlights=row["highlights"],  # type: ignore[arg-type]
        relevance=row["relevance"],  # type: ignore[arg-type]
        similarity=row["similarity"],  # type: ignore[arg-type]
        similarity_threshold_met=bool(row.get("similarity_threshold_met", False)),
        alarm_code_match=row.get("alarm_code_match", "not_requested"),  # type: ignore[arg-type]
        excerpt_is_complete_chunk=bool(row.get("excerpt_is_complete_chunk", False)),
        section_category=row.get("section_category"),  # type: ignore[arg-type]
        section_category_is_inferred=bool(row.get("section_category_is_inferred", True)),
        documented_section_title=row.get("documented_section_title"),  # type: ignore[arg-type]
    )


@app.get("/health")
async def health() -> dict[str, str | bool]:
    """Report API, configuration, and PostgreSQL reachability."""

    settings = get_settings()
    database_reachable = await check_connection()
    return {
        "status": "ok",
        "service": "backend",
        "llm_configured": settings.llm_api_key is not None,
        "database_configured": bool(settings.postgres_password.get_secret_value()),
        "authentication_configured": settings.auth_jwt_secret is not None,
        "database_reachable": database_reachable,
    }


@app.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Authenticate a local password and return a short-lived bearer token."""

    user = await authenticate_password(request.user_id, request.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    return LoginResponse(
        access_token=create_access_token(user),
        user=SessionUser(user_id=user.user_id, company_id=user.company_id, visibility=user.visibility),
    )


@app.get("/auth/me", response_model=SessionUser)
async def current_session(user: AuthContext = Depends(get_current_user)) -> SessionUser:
    """Return the user resolved from the submitted bearer token."""

    return SessionUser(
        user_id=user.user_id,
        company_id=user.company_id,
        visibility=user.visibility,
    )


@app.get("/profile", response_model=UserProfile)
async def profile(user: AuthContext = Depends(get_current_user)) -> UserProfile:
    """Return the signed-in user's own account and company information."""

    details = await get_user_profile(user)
    return UserProfile(**details)


@app.get("/machines", response_model=list[MachineSummary])
async def company_machines(
    user: AuthContext = Depends(get_current_user),
) -> list[MachineSummary]:
    """List machine identity data belonging to the authenticated company."""

    ensure_visibility(user, "machines")
    return [MachineSummary(**row) for row in await get_company_machines(user.company_id)]


@app.get("/machines/lookup/{qr_value}", response_model=MachineContext)
async def lookup_machine_from_qr(
    qr_value: str,
    user: AuthContext = Depends(get_current_user),
) -> MachineContext:
    """Resolve a QR payload containing a machine id or serial number.

    The QR reader belongs in the frontend; this endpoint is the secure backend
    boundary that turns its value into machine context for the chat screen.
    """

    normalized_value = qr_value.strip()
    if not normalized_value or len(normalized_value) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The QR value is invalid.",
        )

    query = """
        SELECT
            m.machine_id,
            m.serial_number,
            m.company_id,
            c.company_name,
            m.model_id,
            mm.model_code,
            mm.description AS model_description,
            m.delivery_date,
            m.plant_location,
            COALESCE(m.configuration_profile, '') AS configuration_profile,
            m.plc_family,
            COALESCE(m.software_version, '') AS software_version
        FROM machines AS m
        JOIN companies AS c ON c.company_id = m.company_id
        JOIN machine_models AS mm ON mm.model_id = m.model_id
        WHERE m.machine_id = %s OR m.serial_number = %s
        LIMIT 1
    """

    try:
        async with connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, (normalized_value, normalized_value))
                row = await cursor.fetchone()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The database is unavailable.",
        ) from error

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No machine matches this QR value.",
        )

    ensure_company_access(user, row[2])
    ensure_visibility(user, "machines")

    (
        machine_id,
        serial_number,
        company_id,
        company_name,
        model_id,
        model_code,
        model_description,
        delivery_date,
        plant_location,
        configuration_profile,
        plc_family,
        software_version,
    ) = row
    return MachineContext(
        machine_id=machine_id,
        serial_number=serial_number,
        company_id=company_id,
        company_name=company_name,
        model_id=model_id,
        model_code=model_code,
        model_description=model_description,
        delivery_date=delivery_date.isoformat() if delivery_date else None,
        plant_location=plant_location,
        plc_family=plc_family,
        software_version=software_version or None,
        configuration_profile=configuration_profile or None,
        operational_context=(
            f"Machine {machine_id} (serial {serial_number}); "
            f"configuration: {configuration_profile or 'n/a'}; "
            f"software: {software_version or 'n/a'}"
        ),
    )


@app.get("/machines/{machine_id}/alarms", response_model=list[AlarmRecord])
async def machine_alarms(
    machine_id: str,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    alarm_code: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    alarm_status: str | None = Query(default=None),
) -> list[AlarmRecord]:
    """IoT Agent endpoint for recent alarms."""

    try:
        rows = await recent_alarms(
            machine_id.strip(), user, limit, start_time=start_time,
            end_time=end_time, alarm_code=alarm_code, severity=severity,
            alarm_status=alarm_status,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    return [AlarmRecord(timestamp=row["timestamp"].isoformat(), **{key: value for key, value in row.items() if key != "timestamp"}) for row in rows]


@app.get("/machines/{machine_id}/alarms/count")
async def machine_alarm_count(
    machine_id: str,
    user: AuthContext = Depends(get_current_user),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    alarm_code: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    alarm_status: str | None = Query(default=None),
) -> dict[str, Any]:
    """Count authorised alarm events using database-side filters."""

    try:
        return await count_alarms(
            machine_id.strip(), user, start_time=start_time, end_time=end_time,
            alarm_code=alarm_code, severity=severity, alarm_status=alarm_status,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except MachineNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found.") from error


@app.get("/machines/{machine_id}/alarms/summary")
async def machine_alarm_summary(
    machine_id: str,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    alarm_code: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    alarm_status: str | None = Query(default=None),
) -> dict[str, Any]:
    """Group authorised alarm events by code."""

    try:
        return await alarm_summary(
            machine_id.strip(), user, limit, start_time=start_time,
            end_time=end_time, alarm_code=alarm_code, severity=severity,
            alarm_status=alarm_status,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except MachineNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found.") from error


@app.get(
    "/machines/{machine_id}/alarms/{alarm_code}/guidance",
    response_model=AlarmGuidance,
)
async def machine_alarm_guidance(
    machine_id: str,
    alarm_code: str,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=5, ge=1, le=10),
) -> AlarmGuidance:
    """Explain one dataset alarm code with cited machine-manual guidance."""

    try:
        bundle = await retrieve_alarm_guidance_evidence(machine_id.strip(), alarm_code, user, limit)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    except ManualsUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Manual search is temporarily unavailable.",
        ) from error

    meaning_result = next(
        result
        for result in bundle.results
        if result.agent == "iot" and result.operation == "alarm_meaning"
    )
    recent_alarms_result = next(
        (
            result
            for result in bundle.results
            if result.agent == "iot" and result.operation == "recent_alarms"
        ),
        None,
    )
    manual_result = next(
        result
        for result in bundle.results
        if result.agent == "manuals" and result.operation == "search"
    )
    report = meaning_result.evidence
    recent_events = recent_alarms_result.evidence["alarms"] if recent_alarms_result else []
    return AlarmGuidance(
        machine_id=machine_id.strip(),
        alarm_code=report["alarm_code"],
        meaning=report["meaning"],
        recent_events=[
            AlarmRecord(
                timestamp=row["timestamp"].isoformat(),
                **{key: value for key, value in row.items() if key != "timestamp"},
            )
            for row in recent_events
        ],
        manual_evidence=[manual_search_result(row) for row in manual_result.evidence["manual_evidence"]],
    )


@app.get("/machines/{machine_id}/telemetry", response_model=list[TelemetryRecord])
async def machine_telemetry(
    machine_id: str,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=24, ge=1, le=100),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    operational_status: str | None = Query(default=None),
) -> list[TelemetryRecord]:
    """IoT Agent endpoint for recent telemetry snapshots."""

    try:
        rows = await telemetry(
            machine_id.strip(), user, limit, start_time=start_time,
            end_time=end_time, operational_status=operational_status,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    return [TelemetryRecord(timestamp=row["timestamp"].isoformat(), **{key: value for key, value in row.items() if key != "timestamp"}) for row in rows]


@app.get("/machines/{machine_id}/telemetry/summary")
async def machine_telemetry_summary(
    machine_id: str,
    user: AuthContext = Depends(get_current_user),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    operational_status: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return database-side telemetry statistics for one window."""

    try:
        return await telemetry_summary(
            machine_id.strip(), user, start_time=start_time, end_time=end_time,
            operational_status=operational_status,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except MachineNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found.") from error


@app.get("/machines/{machine_id}/telemetry/compare")
async def machine_telemetry_comparison(
    machine_id: str,
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
    user: AuthContext = Depends(get_current_user),
    operational_status: str | None = Query(default=None),
) -> dict[str, Any]:
    """Compare database-side telemetry summaries for two explicit periods."""

    try:
        return await compare_telemetry_periods(
            machine_id.strip(), user, first_start=first_start, first_end=first_end,
            second_start=second_start, second_end=second_end,
            operational_status=operational_status,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except MachineNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found.") from error


@app.get(
    "/machines/{machine_id}/maintenance-tickets",
    response_model=list[MaintenanceTicketRecord],
)
async def machine_maintenance_tickets(
    machine_id: str,
    response: Response,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    ticket_id: str | None = None,
    alarm_id: str | None = None,
    ticket_status: str | None = None,
    ticket_type: str | None = None,
    priority: str | None = None,
    owner_role: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[MaintenanceTicketRecord]:
    """Service Agent endpoint for a machine's maintenance history."""

    try:
        result = await search_tickets(
            machine_id, user, limit, ticket_id=ticket_id, alarm_id=alarm_id,
            ticket_status=ticket_status, ticket_type=ticket_type, priority=priority,
            owner_role=owner_role, start_date=start_date, end_date=end_date,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    _list_headers(response, result)
    rows = result["items"]
    return [
        MaintenanceTicketRecord(
            created_date=row["created_date"].isoformat(),
            **{key: value for key, value in row.items() if key != "created_date"},
        )
        for row in rows
    ]


@app.get("/machines/{machine_id}/maintenance-tickets/{ticket_id}", response_model=MaintenanceTicketRecord)
async def machine_ticket_detail(
    machine_id: str, ticket_id: str, user: AuthContext = Depends(get_current_user),
) -> MaintenanceTicketRecord:
    """Return one ticket belonging to an authorised machine."""

    try:
        row = await ticket_detail(machine_id, user, ticket_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MachineNotFoundError as error:
        raise HTTPException(status_code=404, detail="Machine not found.") from error
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket not found.") from error
    return MaintenanceTicketRecord(
        created_date=row["created_date"].isoformat(),
        **{key: value for key, value in row.items() if key != "created_date"},
    )


@app.get(
    "/machines/{machine_id}/maintenance-observation",
    response_model=MaintenanceObservation,
)
async def machine_maintenance_observation(
    machine_id: str,
    user: AuthContext = Depends(get_current_user),
) -> MaintenanceObservation:
    """Compare documented maintenance thresholds with observed productive hours."""

    try:
        report = await retrieve_maintenance_observation(machine_id.strip(), user)
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    return MaintenanceObservation(
        first_snapshot=report["first_snapshot"].isoformat() if report["first_snapshot"] else None,
        last_snapshot=report["last_snapshot"].isoformat() if report["last_snapshot"] else None,
        **{
            key: value
            for key, value in report.items()
            if key not in {"first_snapshot", "last_snapshot"}
        },
    )


@app.get(
    "/machines/{machine_id}/manuals/search",
    response_model=list[ManualSearchResult],
)
async def search_machine_manual(
    machine_id: str,
    query: str = Query(min_length=1, max_length=1_000),
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=5, ge=1, le=10),
) -> list[ManualSearchResult]:
    """Manuals Agent endpoint: semantic search scoped to one authorised machine."""

    normalized_query = query.strip()
    if not normalized_query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The manual search query cannot be blank.",
        )
    try:
        rows = await search_manual(machine_id.strip(), normalized_query, user, limit)
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    except ManualsUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Manual search is temporarily unavailable.",
        ) from error
    return [manual_search_result(row) for row in rows]


@app.get("/machines/{machine_id}/manuals/files/{source_file}")
async def open_machine_manual(
    machine_id: str,
    source_file: str,
    user: AuthContext = Depends(get_current_user),
) -> FileResponse:
    """Serve one authorised local manual inline; it is never a public static file."""

    safe_file_name = Path(source_file).name
    if safe_file_name != source_file or Path(safe_file_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found.")

    try:
        is_available = await can_open_file(machine_id.strip(), safe_file_name, user)
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    if not is_available:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found.")

    manual_path = MANUALS_DIRECTORY / safe_file_name
    if not manual_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual file is unavailable.")
    return FileResponse(
        manual_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_file_name}"'},
    )


def _list_headers(response: Response, result: dict[str, Any]) -> None:
    """Keep list response bodies compatible while exposing completeness."""
    response.headers["X-Total-Count"] = str(result["total_count"])
    response.headers["X-Returned-Count"] = str(result["returned_count"])
    response.headers["X-Is-Truncated"] = str(result["is_truncated"]).lower()
    response.headers["X-Limit"] = str(result["limit"])


@app.get("/orders", response_model=list[OrderRecord])
async def company_orders(
    response: Response,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    machine_id: str | None = None,
    order_id: str | None = None,
    quote_id: str | None = None,
    order_status: str | None = None,
    shipment_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[OrderRecord]:
    """Orders Agent endpoint; company scope comes from the authenticated user."""

    try:
        result = await search_orders(
            user, limit, machine_id=machine_id, order_id=order_id, quote_id=quote_id,
            order_status=order_status, shipment_status=shipment_status,
            start_date=start_date, end_date=end_date,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    _list_headers(response, result)
    rows = result["items"]
    return [OrderRecord(**row) for row in rows]


@app.get("/orders/{order_id}", response_model=OrderDetail)
async def company_order_detail(order_id: str, user: AuthContext = Depends(get_current_user)) -> OrderDetail:
    """Return the approved quote content and fulfilment status of one order."""

    try:
        detail = await order_detail(user, order_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.") from error
    revision = detail["approved_revision"]
    return OrderDetail(
        order_id=detail["order_id"], quote_id=detail["quote_id"], order_status=detail["order_status"],
        shipment_status=detail["shipment_status"], currency=detail["currency"],
        approved_revision=None if revision is None else ApprovedOrderRevision(
            revision_number=revision["revision_number"], revision_status=revision["revision_status"],
            discount_rate=float(revision["discount_rate"]) if revision["discount_rate"] is not None else None,
        ),
        items=[OrderItem(price=float(item["price"]), **{key: value for key, value in item.items() if key != "price"}) for item in detail["items"]],
        fulfillment=[FulfillmentLine(**line) for line in detail["fulfillment"]],
    )


@app.get("/quotes", response_model=list[QuoteRecord])
async def company_quotes(
    response: Response,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    machine_id: str | None = None,
    quote_id: str | None = None,
    revision_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[QuoteRecord]:
    """Orders Agent endpoint for latest quote revisions and totals."""

    try:
        result = await search_quotes(
            user, limit, machine_id=machine_id, quote_id=quote_id,
            revision_status=revision_status, start_date=start_date, end_date=end_date,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    _list_headers(response, result)
    rows = result["items"]
    return [
        QuoteRecord(
            valid_until=row["valid_until"].isoformat() if row["valid_until"] else None,
            validity_status=row["validity_status"],
            discount_rate=float(row["discount_rate"]) if row["discount_rate"] is not None else None,
            line_total=float(row["line_total"]),
            **{
                key: value
                for key, value in row.items()
                if key not in {"valid_until", "validity_status", "discount_rate", "line_total"}
            },
        )
        for row in rows
    ]


@app.get("/quotes/{quote_id}", response_model=QuoteHistory)
async def company_quote_history(
    quote_id: str,
    user: AuthContext = Depends(get_current_user),
) -> QuoteHistory:
    """Return all authorised revisions, lines, and latest revision changes."""

    try:
        history = await quote_history(user, quote_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except QuoteNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found.",
        ) from error

    return QuoteHistory(
        valid_until=history["valid_until"].isoformat() if history["valid_until"] else None,
        validity_status=history["validity_status"],
        currency=history["currency"],
        created_at=history["created_at"],
        description=history["description"],
        quote_id=history["quote_id"],
        revisions=[
            QuoteRevisionDetail(
                discount_rate=float(revision["discount_rate"]) if revision["discount_rate"] is not None else None,
                line_total=float(revision["line_total"]),
                lines=[
                    QuoteLineDetail(price=float(line["price"]), **{key: value for key, value in line.items() if key != "price"})
                    for line in revision["lines"]
                ],
                **{
                    key: value
                    for key, value in revision.items()
                    if key not in {"discount_rate", "line_total", "lines"}
                },
            )
            for revision in history["revisions"]
        ],
        comparison_basis=history.get("comparison_basis"),
        latest_comparison=[
            QuoteLineChange(
                previous_price=float(change["previous_price"]) if change["previous_price"] is not None else None,
                current_price=float(change["current_price"]) if change["current_price"] is not None else None,
                **{key: value for key, value in change.items() if key not in {"previous_price", "current_price"}},
            )
            for change in history["latest_comparison"]
        ],
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: AuthContext = Depends(get_current_user),
) -> ChatResponse:
    """Send a question to the configured LLM (agent routing comes next)."""

    message = request.message.strip()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The message cannot be blank.",
        )

    try:
        result = await handle_chat(
            message,
            replace(user, hide_machine_existence=True),
            request.machine_id,
            request.history,
        )
    except MissingMachineContextError as error:
        return ChatResponse(answer=str(error))
    except (MachineNotFoundError, MachineUnavailableError):
        return ChatResponse(
            answer=(
                "The requested machine is not available in your authorized scope, "
                "so I cannot provide machine-specific information."
            )
        )
    except ManualsUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Manual search is temporarily unavailable.",
        ) from None
    except LlmNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM_API_KEY is not configured.",
        ) from None
    except LlmRequestError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The LLM provider could not complete the request.",
        ) from None

    return ChatResponse(
        answer=result.answer,
        agent=result.agent,
        sources=[manual_search_result(row) for row in result.manual_evidence or []],
        data=result.structured_data,
    )
