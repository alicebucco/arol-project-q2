"""Operations API endpoints."""

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from agents.iot import alarm_summary, compare_telemetry_periods, count_alarms, recent_alarms, telemetry, telemetry_summary
from agents.manuals import ManualsUnavailableError
from agents.service import search_tickets, ticket_detail
from api.pagination import _list_headers
from api.presenters import manual_search_result
from api.schemas import AlarmGuidance, AlarmRecord, MaintenanceObservation, MaintenanceTicketRecord, TelemetryRecord
from core.auth import AuthContext, get_current_user
from db.repositories.errors import MachineNotFoundError, TicketNotFoundError
from core.orchestrator import retrieve_alarm_guidance_evidence, retrieve_maintenance_observation

router = APIRouter()

@router.get("/machines/{machine_id}/alarms", response_model=list[AlarmRecord])
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

@router.get("/machines/{machine_id}/alarms/count")
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

@router.get("/machines/{machine_id}/alarms/summary")
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

@router.get("/machines/{machine_id}/alarms/{alarm_code}/guidance", response_model=AlarmGuidance)
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

@router.get("/machines/{machine_id}/telemetry", response_model=list[TelemetryRecord])
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

@router.get("/machines/{machine_id}/telemetry/summary")
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

@router.get("/machines/{machine_id}/telemetry/compare")
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

@router.get("/machines/{machine_id}/maintenance-tickets", response_model=list[MaintenanceTicketRecord])
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

@router.get("/machines/{machine_id}/maintenance-tickets/{ticket_id}", response_model=MaintenanceTicketRecord)
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

@router.get("/machines/{machine_id}/maintenance-observation", response_model=MaintenanceObservation)
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
