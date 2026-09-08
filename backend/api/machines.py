"""Machines API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas import MachineContext, MachineSummary
from core.auth import AuthContext, ensure_company_access, ensure_visibility, get_current_user
from db.repositories.machines import get_company_machines
from core.db import connection

router = APIRouter()

@router.get("/machines", response_model=list[MachineSummary])
async def company_machines(
    user: AuthContext = Depends(get_current_user),
) -> list[MachineSummary]:
    """List machine identity data belonging to the authenticated company."""

    ensure_visibility(user, "machines")
    return [MachineSummary(**row) for row in await get_company_machines(user.company_id)]

@router.get("/machines/lookup/{qr_value}", response_model=MachineContext)
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
