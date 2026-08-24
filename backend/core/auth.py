"""Authentication/session boundary and role-based data scope.

The workbook has no password or identity-provider fields, so the current
development adapter resolves ``X-User-Id`` against the ``users`` table. A real
deployment can replace this dependency with JWT/session verification without
changing the data-access code.
"""

from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from core.db import connection


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    company_id: str
    visibility: str


async def get_current_user(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> AuthContext:
    """Resolve the authenticated development session from the database."""

    if not x_user_id or not x_user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        async with connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT user_id, company_id, visibility
                    FROM users
                    WHERE user_id = %s
                    """,
                    (x_user_id.strip(),),
                )
                row = await cursor.fetchone()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The authentication service is unavailable.",
        ) from error

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication.",
        )

    return AuthContext(user_id=row[0], company_id=row[1], visibility=row[2])


def ensure_company_access(user: AuthContext, resource_company_id: str) -> None:
    """Reject cross-tenant access with the explicit project error contract."""

    if user.company_id != resource_company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )


def ensure_visibility(user: AuthContext, domain: str) -> None:
    """Enforce the dataset visibility matrix for future data endpoints."""

    allowed = {
        "machines": {"full", "technician", "commercial"},
        "operational": {"full", "technician"},
        "commercial": {"full", "commercial"},
        "manuals": {"full", "technician", "commercial"},
    }
    if user.visibility not in allowed.get(domain, set()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )
