"""JWT authentication and server-side tenant/role enforcement."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import get_settings
from core.db import connection


JWT_ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    company_id: str
    visibility: str
    hide_machine_existence: bool = False


def _auth_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication is not configured.",
    )


def _jwt_secret() -> str:
    secret = get_settings().auth_jwt_secret
    if secret is None or not secret.get_secret_value().strip():
        raise _auth_unavailable()
    return secret.get_secret_value()


async def _user_context(user_id: str) -> AuthContext | None:
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT user_id, company_id, visibility FROM users WHERE user_id = %s",
                (user_id,),
            )
            row = await cursor.fetchone()
    if row is None:
        return None
    return AuthContext(user_id=row[0], company_id=row[1], visibility=row[2])


async def authenticate_password(user_id: str, password: str) -> AuthContext | None:
    """Verify a bcrypt password for a synthetic local user."""

    try:
        async with connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT user_id, company_id, visibility, password_hash FROM users WHERE user_id = %s",
                    (user_id.strip().upper(),),
                )
                row = await cursor.fetchone()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The authentication service is unavailable.",
        ) from error

    if row is None or row[3] is None:
        return None
    try:
        valid = bcrypt.checkpw(password.encode("utf-8"), row[3].encode("utf-8"))
    except ValueError:
        valid = False
    if not valid:
        return None
    return AuthContext(user_id=row[0], company_id=row[1], visibility=row[2])


def create_access_token(user: AuthContext) -> str:
    """Create a short-lived JWT; role and company remain checked from the DB."""

    settings = get_settings()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=settings.auth_jwt_expire_minutes)
    return jwt.encode({"sub": user.user_id, "exp": expiry}, _jwt_secret(), algorithm=JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext:
    """Resolve a bearer JWT and re-read current tenant/role from the database."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    try:
        payload = jwt.decode(credentials.credentials, _jwt_secret(), algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not isinstance(user_id, str) or not user_id.strip():
            raise jwt.InvalidTokenError("Missing subject")
        user = await _user_context(user_id)
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.") from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The authentication service is unavailable.",
        ) from error

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication.")
    return user


def ensure_company_access(user: AuthContext, resource_company_id: str) -> None:
    """Reject cross-tenant access with the explicit project error contract."""

    if user.company_id != resource_company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


def ensure_visibility(user: AuthContext, domain: str) -> None:
    """Enforce the dataset visibility matrix server-side."""

    allowed = {
        "machines": {"full", "technician", "commercial"},
        "operational": {"full", "technician"},
        "commercial": {"full", "commercial"},
        "manuals": {"full", "technician", "commercial"},
    }
    if user.visibility not in allowed.get(domain, set()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
