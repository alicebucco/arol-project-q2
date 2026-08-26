"""FastAPI entry point for the AROL Customer Platform backend."""

from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.auth import AuthContext, ensure_company_access, ensure_visibility, get_current_user
from core.config import get_settings
from core.db import check_connection, connection
from core.data_access import MachineNotFoundError
from core.llm import LlmNotConfiguredError, LlmRequestError, generate_chat_reply
from agents.iot import recent_alarms, telemetry
from agents.service import maintenance_tickets
from agents.orders import orders, quotes
from agents.manuals import ManualsUnavailableError, search as search_manual


app = FastAPI(title="AROL Customer Platform API", version="0.1.0")


class ChatRequest(BaseModel):
    """Temporary chat input before sessions and machine context are added."""

    message: str = Field(min_length=1, max_length=4_000)


class ChatResponse(BaseModel):
    """Temporary chat output before agents and citations are added."""

    answer: str


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
    operational_context: str


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


class MaintenanceTicketRecord(BaseModel):
    ticket_id: str
    alarm_id: str | None = None
    ticket_type: str
    ticket_status: str
    priority: str
    created_date: str
    owner_role: str


class OrderRecord(BaseModel):
    order_id: str
    quote_id: str
    order_status: str
    shipment_status: str


class QuoteRecord(BaseModel):
    quote_id: str
    valid_until: str | None = None
    revision_number: int | None = None
    revision_status: str | None = None
    discount_rate: float | None = None
    line_total: float


class ManualCitation(BaseModel):
    source: Literal["manual"]
    file: str
    page: int
    section: str


class ManualSearchResult(BaseModel):
    citation: ManualCitation
    content: str
    similarity: float


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
        "database_reachable": database_reachable,
    }


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
            m.plant_location,
            COALESCE(m.configuration_profile, '') AS configuration_profile,
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
        plant_location,
        configuration_profile,
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
        plant_location=plant_location,
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
) -> list[AlarmRecord]:
    """IoT Agent endpoint for recent alarms."""

    try:
        rows = await recent_alarms(machine_id.strip(), user, limit)
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    return [AlarmRecord(timestamp=row["timestamp"].isoformat(), **{key: value for key, value in row.items() if key != "timestamp"}) for row in rows]


@app.get("/machines/{machine_id}/telemetry", response_model=list[TelemetryRecord])
async def machine_telemetry(
    machine_id: str,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=24, ge=1, le=100),
) -> list[TelemetryRecord]:
    """IoT Agent endpoint for recent telemetry snapshots."""

    try:
        rows = await telemetry(machine_id.strip(), user, limit)
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    return [TelemetryRecord(timestamp=row["timestamp"].isoformat(), **{key: value for key, value in row.items() if key != "timestamp"}) for row in rows]


@app.get(
    "/machines/{machine_id}/maintenance-tickets",
    response_model=list[MaintenanceTicketRecord],
)
async def machine_maintenance_tickets(
    machine_id: str,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[MaintenanceTicketRecord]:
    """Service Agent endpoint for a machine's maintenance history."""

    try:
        rows = await maintenance_tickets(machine_id.strip(), user, limit)
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    return [
        MaintenanceTicketRecord(
            created_date=row["created_date"].isoformat(),
            **{key: value for key, value in row.items() if key != "created_date"},
        )
        for row in rows
    ]


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
    return [
        ManualSearchResult(
            citation=ManualCitation(
                source=row["source"],
                file=row["file"],
                page=row["page"],
                section=row["section"],
            ),
            content=row["content"],
            similarity=row["similarity"],
        )
        for row in rows
    ]


@app.get("/orders", response_model=list[OrderRecord])
async def company_orders(
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[OrderRecord]:
    """Orders Agent endpoint; company scope comes from the authenticated user."""

    rows = await orders(user, limit)
    return [OrderRecord(**row) for row in rows]


@app.get("/quotes", response_model=list[QuoteRecord])
async def company_quotes(
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[QuoteRecord]:
    """Orders Agent endpoint for latest quote revisions and totals."""

    rows = await quotes(user, limit)
    return [
        QuoteRecord(
            valid_until=row["valid_until"].isoformat() if row["valid_until"] else None,
            discount_rate=float(row["discount_rate"]) if row["discount_rate"] is not None else None,
            line_total=float(row["line_total"]),
            **{key: value for key, value in row.items() if key not in {"valid_until", "discount_rate", "line_total"}},
        )
        for row in rows
    ]


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
        answer = await generate_chat_reply(message)
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

    return ChatResponse(answer=answer)
