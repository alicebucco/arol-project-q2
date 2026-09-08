"""PostgreSQL repository for machines data."""

from dataclasses import dataclass
from typing import Any

from core.auth import AuthContext, ensure_company_access, ensure_visibility
from core.db import connection
from db.repositories.errors import MachineNotFoundError, MachineUnavailableError


@dataclass(frozen=True)
class MachineScope:
    machine_id: str
    company_id: str

async def authorize_machine(
    machine_id: str,
    user: AuthContext,
    domain: str = "operational",
) -> MachineScope:
    """Resolve a machine and enforce tenant + visibility before querying data."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT machine_id, company_id FROM machines WHERE machine_id = %s",
                (machine_id,),
            )
            row = await cursor.fetchone()

    if row is None and user.hide_machine_existence:
        raise MachineUnavailableError(machine_id)
    if row is None:
        raise MachineNotFoundError(machine_id)
    if user.company_id != row[1] and user.hide_machine_existence:
        raise MachineUnavailableError(machine_id)
    ensure_company_access(user, row[1])
    ensure_visibility(user, domain)
    return MachineScope(machine_id=row[0], company_id=row[1])

async def get_company_machines(company_id: str) -> list[dict[str, Any]]:
    """Return the machine identity data visible to every user in one company."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT m.machine_id, m.serial_number, mm.model_code, mm.description,
                       m.plant_location, m.configuration_profile
                FROM machines AS m
                JOIN machine_models AS mm ON mm.model_id = m.model_id
                WHERE m.company_id = %s
                ORDER BY m.machine_id
                """,
                (company_id,),
            )
            rows = await cursor.fetchall()
    return [
        {
            "machine_id": row[0],
            "serial_number": row[1],
            "model_code": row[2],
            "model_description": row[3],
            "plant_location": row[4],
            "configuration_profile": row[5],
        }
        for row in rows
    ]

async def get_user_profile(user: AuthContext) -> dict[str, Any]:
    """Return the authenticated user's own account and company context."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT u.user_id, u.first_name, u.last_name, u.email, u.job_title, u.visibility,
                       c.company_id, c.company_name, c.country, c.city, c.sector, c.currency, c.locale
                FROM users AS u
                JOIN companies AS c ON c.company_id = u.company_id
                WHERE u.user_id = %s AND u.company_id = %s
                """,
                (user.user_id, user.company_id),
            )
            row = await cursor.fetchone()
    if row is None:
        raise LookupError(user.user_id)
    return {
        "user_id": row[0], "first_name": row[1], "last_name": row[2], "email": row[3],
        "job_title": row[4], "visibility": row[5], "company_id": row[6],
        "company_name": row[7], "country": row[8], "city": row[9], "sector": row[10],
        "currency": row[11], "locale": row[12],
    }
