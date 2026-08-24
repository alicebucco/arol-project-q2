"""Small PostgreSQL connection helper used by the API health check.

The application opens short-lived async connections for now. Agents will later
reuse this boundary for parameterised queries, keeping database credentials and
tenant/access filters outside of model-generated prompts.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from psycopg import AsyncConnection

from core.config import get_settings


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection]:
    """Yield an async PostgreSQL connection configured from the environment."""

    settings = get_settings()
    conn = await AsyncConnection.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        dbname=settings.postgres_db,
        connect_timeout=settings.postgres_connect_timeout,
    )
    try:
        yield conn
    finally:
        await conn.close()


async def check_connection() -> bool:
    """Return whether PostgreSQL accepts a connection and a trivial query."""

    try:
        async with connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
                await cursor.fetchone()
        return True
    except Exception:
        # Health must remain useful while the database is starting up or absent.
        return False
