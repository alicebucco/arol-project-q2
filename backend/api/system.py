"""System API endpoints."""

from fastapi import APIRouter

from core.config import get_settings
from core.db import check_connection

router = APIRouter()

@router.get("/health")
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

