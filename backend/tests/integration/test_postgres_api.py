"""API integration tests backed by an isolated PostgreSQL instance."""

import os
from collections.abc import Iterator

import bcrypt
import psycopg
import pytest
from fastapi.testclient import TestClient

import main
from core.config import get_settings


INTEGRATION_PASSWORD = "integration-password"
INTEGRATION_DATABASE = "arol_integration"
INTEGRATION_HOST = os.getenv("INTEGRATION_POSTGRES_HOST", "127.0.0.1")
INTEGRATION_PORT = os.getenv("INTEGRATION_POSTGRES_PORT", "55432")


def _enabled() -> bool:
    return os.getenv("RUN_DB_INTEGRATION") == "1"


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _enabled(),
        reason="Set RUN_DB_INTEGRATION=1 after starting docker-compose.integration.yml.",
    ),
]


@pytest.fixture(scope="session", autouse=True)
def integration_environment() -> Iterator[None]:
    """Force every integration connection to the disposable Docker database."""

    values = {
        "POSTGRES_HOST": INTEGRATION_HOST,
        "POSTGRES_PORT": INTEGRATION_PORT,
        "POSTGRES_USER": "integration_user",
        "POSTGRES_PASSWORD": "integration_password",
        "POSTGRES_DB": INTEGRATION_DATABASE,
        "AUTH_JWT_SECRET": "integration-jwt-secret",
    }
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    get_settings.cache_clear()
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def isolated_database(integration_environment: None) -> Iterator[None]:
    """Seed only the disposable database and remove the records afterwards."""

    get_settings.cache_clear()
    settings = get_settings()
    if settings.postgres_db != INTEGRATION_DATABASE:
        raise RuntimeError("Integration tests must use the isolated arol_integration database.")

    password_hash = bcrypt.hashpw(INTEGRATION_PASSWORD.encode(), bcrypt.gensalt()).decode()
    with psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        dbname=settings.postgres_db,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE users, machines, machine_models, companies CASCADE")
            cursor.execute(
                """INSERT INTO companies (company_id, company_name, country, city, sector, currency, locale)
                   VALUES ('CMP-TEST', 'Integration Company', 'Italy', 'Turin', 'Beverages', 'EUR', 'en-GB')"""
            )
            cursor.execute(
                """INSERT INTO machine_models (model_id, model_code, description)
                   VALUES ('MDL-TEST', 'TEST-CLOSER', 'Integration test closer')"""
            )
            cursor.execute(
                """INSERT INTO machines (machine_id, company_id, model_id, serial_number, plant_location, configuration_profile)
                   VALUES ('MCH-TEST', 'CMP-TEST', 'MDL-TEST', 'SERIAL-TEST', 'Integration Plant', 'Test configuration')"""
            )
            cursor.execute(
                """INSERT INTO users (user_id, company_id, first_name, last_name, email, job_title, visibility, password_hash)
                   VALUES ('USR-TEST', 'CMP-TEST', 'Test', 'User', 'test@example.com', 'Engineer', 'full', %s)""",
                (password_hash,),
            )
        conn.commit()

    yield

    with psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        dbname=settings.postgres_db,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE users, machines, machine_models, companies CASCADE")
        conn.commit()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(main.app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_login_and_company_machine_access_use_real_postgres_and_jwt(client: TestClient) -> None:
    login = client.post("/auth/login", json={"user_id": "USR-TEST", "password": INTEGRATION_PASSWORD})

    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    session = client.get("/auth/me", headers=headers)
    machines = client.get("/machines", headers=headers)
    machine = client.get("/machines/lookup/MCH-TEST", headers=headers)

    assert session.status_code == 200
    assert session.json() == {"user_id": "USR-TEST", "company_id": "CMP-TEST", "visibility": "full"}
    assert machines.status_code == 200
    assert machines.json()[0]["machine_id"] == "MCH-TEST"
    assert machine.status_code == 200
    assert machine.json()["company_id"] == "CMP-TEST"


def test_machine_api_rejects_missing_or_invalid_jwt(client: TestClient) -> None:
    assert client.get("/machines").status_code == 401
    assert client.get("/machines", headers={"Authorization": "Bearer invalid-token"}).status_code == 401
