"""API integration tests backed by an isolated PostgreSQL instance."""

import os
import asyncio
from collections.abc import Iterator

import bcrypt
import psycopg
import pytest
from fastapi.testclient import TestClient

import main
from core.data_access import find_manual_alarm_code_matches, search_manual_chunks
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


def test_commercial_filters_totals_history_and_tenant_scope(client: TestClient) -> None:
    """Exercise actual SQL on the disposable database, including omitted page rows."""
    settings = get_settings()
    with psycopg.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        user=settings.postgres_user, password=settings.postgres_password.get_secret_value(),
        dbname=settings.postgres_db,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""INSERT INTO companies
                (company_id, company_name, country, city, sector, currency, locale)
                VALUES ('CMP-OTHER', 'Other', 'Italy', 'Turin', 'Beverages', 'EUR', 'en-GB')""")
            cursor.execute("""INSERT INTO quotes (quote_id, company_id, valid_until, source_data) VALUES
                ('QTE-A', 'CMP-TEST', '2026-08-05', '{"currency":"EUR","created_at":"2026-01-01"}'),
                ('QTE-B', 'CMP-TEST', '2026-08-05', '{"currency":"EUR","created_at":"2026-01-02"}'),
                ('QTE-OTHER', 'CMP-OTHER', NULL, '{}')""")
            cursor.execute("""INSERT INTO quote_revisions
                (quote_revision_id, quote_id, revision_number, revision_status, discount_rate, source_data) VALUES
                ('REV-A1', 'QTE-A', 1, 'Approved', 0.1, '{"change_summary":"Initial proposal"}'),
                ('REV-A2', 'QTE-A', 2, 'Rejected', 0.2, '{"change_summary":"Replacement rejected"}'),
                ('REV-B1', 'QTE-B', 1, 'Approved', 0, '{}')""")
            cursor.execute("""INSERT INTO quote_lines
                (quote_line_id, quote_revision_id, machine_id, price, source_data) VALUES
                ('LINE-A1', 'REV-A1', 'MCH-TEST', 90, '{"description":"Kit"}'),
                ('LINE-A2', 'REV-A2', 'MCH-TEST', 80, '{"description":"Kit"}'),
                ('LINE-A3', 'REV-A2', NULL, 20, '{"description":"Shipping"}'),
                ('LINE-B1', 'REV-B1', 'MCH-TEST', 50, '{"description":"Kit"}')""")
            cursor.execute("""INSERT INTO orders
                (order_id, quote_id, company_id, order_status, shipment_status, source_data) VALUES
                ('ORD-A', 'QTE-A', 'CMP-TEST', 'Confirmed', 'In production',
                 '{"currency":"EUR","order_date":"2026-01-03"}'),
                ('ORD-OTHER', 'QTE-OTHER', 'CMP-OTHER', 'Confirmed', 'In production', '{}')""")
        conn.commit()
    login = client.post("/auth/login", json={"user_id": "USR-TEST", "password": INTEGRATION_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    page = client.get("/quotes?limit=1", headers=headers)
    assert page.status_code == 200
    assert page.headers["X-Total-Count"] == "2"
    assert page.headers["X-Is-Truncated"] == "true"
    selected = client.get(
        "/quotes?machine_id=MCH-TEST&revision_status=Rejected&start_date=2026-01-01&end_date=2026-01-01",
        headers=headers,
    )
    assert selected.status_code == 200
    assert selected.headers["X-Total-Count"] == "1"
    assert selected.json()[0]["line_total"] == 100  # Include shipping; never discount twice.
    assert selected.json()[0]["currency"] == "EUR"
    empty = client.get("/quotes?quote_id=QTE-OTHER", headers=headers)
    assert empty.json() == []
    assert empty.headers["X-Total-Count"] == "0"
    assert empty.headers["X-Is-Truncated"] == "false"
    assert client.get("/quotes/QTE-OTHER", headers=headers).status_code == 404
    assert client.get("/orders/ORD-OTHER", headers=headers).status_code == 404
    orders = client.get(
        "/orders?machine_id=MCH-TEST&order_status=Confirmed&shipment_status=In%20production"
        "&start_date=2026-01-03&end_date=2026-01-03", headers=headers,
    )
    assert orders.status_code == 200
    assert [row["order_id"] for row in orders.json()] == ["ORD-A"]
    detail = client.get("/orders/ORD-A", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["approved_revision"]["revision_number"] == 1
    assert detail.json()["items"][0]["price"] == 90
    history = client.get("/quotes/QTE-A", headers=headers)
    assert history.status_code == 200
    assert history.json()["revisions"][1]["change_summary"] == "Replacement rejected"
    assert history.json()["comparison_basis"]


def test_service_ticket_filters_completeness_and_authorisation(client: TestClient) -> None:
    """Exercise real ticket queries without requiring an associated alarm."""
    settings = get_settings()
    with psycopg.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        user=settings.postgres_user, password=settings.postgres_password.get_secret_value(),
        dbname=settings.postgres_db,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""INSERT INTO companies
                (company_id, company_name, country, city, sector, currency, locale)
                VALUES ('CMP-SERVICE', 'Service test', 'Italy', 'Turin', 'Beverages', 'EUR', 'en-GB')""")
            cursor.execute("""INSERT INTO machines (machine_id, company_id, model_id, serial_number)
                VALUES ('MCH-SERVICE', 'CMP-SERVICE', 'MDL-TEST', 'SERIAL-SERVICE')""")
            cursor.execute("""INSERT INTO alarms
                (alarm_id, machine_id, timestamp, alarm_code, severity, alarm_status)
                VALUES ('ALM-SERVICE', 'MCH-TEST', '2026-01-01', 'AL017_LOW_AIR_PRESSURE', 'High', 'Open')""")
            cursor.execute("""INSERT INTO maintenance_tickets
                (ticket_id, machine_id, alarm_id, ticket_type, ticket_status, priority, created_date, owner_role)
                VALUES
                ('TCK-A', 'MCH-TEST', NULL, 'Scheduled maintenance', 'Open', 'High', '2026-01-01', 'Maintenance Man'),
                ('TCK-B', 'MCH-TEST', 'ALM-SERVICE', 'Remote troubleshooting', 'Closed', 'Low', '2026-01-01', 'AROL Technical Service'),
                ('TCK-OTHER', 'MCH-SERVICE', NULL, 'Overhaul', 'Open', 'High', '2026-01-01', 'Maintenance Man')""")
            password_hash = bcrypt.hashpw(INTEGRATION_PASSWORD.encode(), bcrypt.gensalt()).decode()
            cursor.execute("""INSERT INTO users
                (user_id, company_id, first_name, last_name, email, job_title, visibility, password_hash)
                VALUES ('USR-COMMERCIAL', 'CMP-TEST', 'Commercial', 'User', 'commercial@example.com', 'Sales', 'commercial', %s)""",
                (password_hash,))
        conn.commit()
    login = client.post("/auth/login", json={"user_id": "USR-TEST", "password": INTEGRATION_PASSWORD})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    base = "/machines/MCH-TEST/maintenance-tickets"
    page = client.get(base + "?limit=1", headers=headers)
    assert page.status_code == 200
    assert page.headers["X-Total-Count"] == "2"
    assert page.headers["X-Is-Truncated"] == "true"
    assert page.json()[0]["ticket_id"] == "TCK-B"
    filtered = client.get(base + "?ticket_status=Open&ticket_type=Scheduled%20maintenance&priority=High"
                          "&owner_role=Maintenance%20Man&start_date=2026-01-01&end_date=2026-01-01", headers=headers)
    assert filtered.status_code == 200
    assert filtered.headers["X-Total-Count"] == "1"
    assert filtered.headers["X-Is-Truncated"] == "false"
    assert filtered.json()[0]["ticket_id"] == "TCK-A"
    assert filtered.json()[0]["alarm_id"] is None
    alarm = client.get(base + "?alarm_id=ALM-SERVICE", headers=headers)
    assert [row["ticket_id"] for row in alarm.json()] == ["TCK-B"]
    empty = client.get(base + "?ticket_status=Resolved", headers=headers)
    assert empty.json() == []
    assert empty.headers["X-Total-Count"] == "0"
    assert client.get(base + "/TCK-A", headers=headers).json()["alarm_id"] is None
    assert client.get(base + "/TCK-OTHER", headers=headers).status_code == 404
    assert client.get("/machines/MCH-SERVICE/maintenance-tickets", headers=headers).status_code == 403
    commercial_login = client.post("/auth/login", json={"user_id": "USR-COMMERCIAL", "password": INTEGRATION_PASSWORD})
    commercial_headers = {"Authorization": f"Bearer {commercial_login.json()['access_token']}"}
    assert client.get(base, headers=commercial_headers).status_code == 403
    assert client.get(base + "/TCK-A", headers=commercial_headers).status_code == 403


def test_manual_alarm_code_lookup_uses_whole_code_boundaries() -> None:
    """Verify exact-code evidence against PostgreSQL, not semantic retrieval."""

    settings = get_settings()
    vector_values = [1.0] + [0.0] * 383
    vector = "[" + ",".join(str(value) for value in vector_values) + "]"
    with psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        dbname=settings.postgres_db,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO manual_chunks
                    (chunk_id, machine_id, source_file, page, section, chunk_index, embedding, content)
                VALUES
                    ('MCH-TEST-p1-1', 'MCH-TEST', 'test_manual_EN.pdf', 1, 'troubleshooting', 1, %s::vector,
                     'The literal code AL017_LOW_AIR_PRESSURE is indexed here.'),
                    ('MCH-TEST-p1-2', 'MCH-TEST', 'test_manual_EN.pdf', 1, 'troubleshooting', 2, %s::vector,
                     'AL017_LOW_AIR_PRESSURE_EXTRA must not satisfy the shorter code lookup.')
                """,
                (vector, vector),
            )
        conn.commit()

    matches = asyncio.run(
        find_manual_alarm_code_matches(
            "MCH-TEST",
            ["AL017_LOW_AIR_PRESSURE", "AL083_FALLEN_BOTTLE_ALARM"],
        )
    )

    assert matches == ["AL017_LOW_AIR_PRESSURE"]
    chunks = asyncio.run(search_manual_chunks("MCH-TEST", vector_values, 5))
    assert chunks[0]["chunk_id"] == "MCH-TEST-p1-1"
