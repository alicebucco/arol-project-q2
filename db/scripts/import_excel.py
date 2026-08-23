from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from psycopg.rows import dict_row


SHEETS: dict[str, tuple[str, set[str]]] = {
    "Companies": ("companies", {"company_id", "company_name", "country", "city", "sector", "currency", "locale"}),
    "Users": ("users", {"user_id", "company_id", "first_name", "last_name", "email", "job_title", "visibility"}),
    "MachineModels": ("machine_models", {"model_id", "model_code", "description", "primitive_diameter", "nominal_heads", "container_type", "cap_type", "industry_segment", "notes"}),
    "Machines": ("machines", {"machine_id", "company_id", "model_id", "serial_number", "delivery_date", "plant_location", "configuration_profile", "plc_family", "software_version"}),
    "Quotes": ("quotes", {"quote_id", "company_id", "valid_until"}),
    "QuoteRevisions": ("quote_revisions", {"quote_revision_id", "quote_id", "revision_number", "revision_status", "discount_rate"}),
    "QuoteLines": ("quote_lines", {"quote_line_id", "quote_revision_id", "machine_id", "price"}),
    "Orders": ("orders", {"order_id", "quote_id", "company_id", "order_status", "shipment_status"}),
    "OrderLines": ("order_lines", {"order_line_id", "order_id", "fulfillment_status"}),
    "TelemetrySnapshots": ("telemetry_snapshots", {"telemetry_id", "machine_id", "timestamp", "operational_status", "production_rate_bph", "uptime_percentage", "alarm_count", "temperature_c", "energy_kwh", "health_note"}),
    "Alarms": ("alarms", {"alarm_id", "machine_id", "timestamp", "alarm_code", "severity", "alarm_status"}),
    "MaintenanceTickets": ("maintenance_tickets", {"ticket_id", "machine_id", "alarm_id", "ticket_type", "ticket_status", "priority", "created_date", "owner_role"}),
}

REQUIRED: dict[str, set[str]] = {
    "companies": {"company_id", "company_name", "country", "city", "sector", "currency", "locale"},
    "users": {"user_id", "company_id", "first_name", "last_name", "email", "job_title", "visibility"},
    "machine_models": {"model_id", "model_code"},
    "machines": {"machine_id", "company_id", "model_id", "serial_number"},
    "quotes": {"quote_id", "company_id"},
    "quote_revisions": {"quote_revision_id", "quote_id", "revision_number", "revision_status"},
    "quote_lines": {"quote_line_id", "quote_revision_id"},
    "orders": {"order_id", "quote_id", "company_id", "order_status", "shipment_status"},
    "order_lines": {"order_line_id", "order_id", "fulfillment_status"},
    "telemetry_snapshots": {"telemetry_id", "machine_id", "timestamp", "operational_status", "production_rate_bph", "uptime_percentage", "alarm_count"},
    "alarms": {"alarm_id", "machine_id", "timestamp", "alarm_code", "severity", "alarm_status"},
    "maintenance_tickets": {"ticket_id", "machine_id", "ticket_type", "ticket_status", "priority", "created_date", "owner_role"},
}


def snake_case(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", str(name).strip())
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower().strip("_")


def db_url() -> str:
    if value := os.getenv("DATABASE_URL"):
        return value
    required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SystemExit(
            f"Missing variables: {', '.join(missing)}. Set DATABASE_URL or the POSTGRES_* variables."
        )
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}@{host}:{port}/{os.environ['POSTGRES_DB']}"


def clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, (datetime, date, Decimal, int, float, str, bool)):
        return value
    return str(value)


def read_workbook(path: Path) -> dict[str, list[dict[str, Any]]]:
    workbook = pd.ExcelFile(path)
    missing_sheets = set(SHEETS) - set(workbook.sheet_names)
    if missing_sheets:
        raise ValueError(f"Missing workbook sheets: {', '.join(sorted(missing_sheets))}")

    imported: dict[str, list[dict[str, Any]]] = {}
    for sheet, (table, known_columns) in SHEETS.items():
        frame = pd.read_excel(workbook, sheet_name=sheet)
        frame.columns = [snake_case(column) for column in frame.columns]
        missing_columns = REQUIRED[table] - set(frame.columns)
        if missing_columns:
            raise ValueError(f"{sheet}: missing required columns: {', '.join(sorted(missing_columns))}")
        if frame.empty:
            raise ValueError(f"{sheet}: sheet is empty")

        rows: list[dict[str, Any]] = []
        for raw_row in frame.to_dict(orient="records"):
            row = {column: clean_value(value) for column, value in raw_row.items()}
            source_data = {column: value for column, value in row.items() if column not in known_columns and value is not None}
            rows.append({column: row.get(column) for column in known_columns} | {"source_data": json.dumps(source_data, default=str)})
        imported[table] = rows
    return imported


def import_rows(connection: psycopg.Connection, data: dict[str, list[dict[str, Any]]], replace: bool) -> None:
    tables = [table for table, _ in SHEETS.values()]
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT EXISTS (SELECT 1 FROM companies)")
        is_populated = cursor.fetchone()["exists"]
        if is_populated and not replace:
            raise ValueError("The database already contains data. Run again with --replace to reload the dataset.")
        if replace:
            cursor.execute("TRUNCATE TABLE " + ", ".join(tables) + " CASCADE")

        for table in tables:
            rows = data[table]
            columns = sorted(rows[0])
            sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('%s' for _ in columns)})"
            cursor.executemany(sql, [[row[column] for column in columns] for row in rows])
            print(f"{table}: {len(rows)} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the AROL Excel workbook into PostgreSQL (PDFs excluded).")
    parser.add_argument("workbook", type=Path, help="Path to AROL_Q2_synthetic_fleet_dataset.xlsx")
    parser.add_argument("--replace", action="store_true", help="Replace all existing relational data")
    args = parser.parse_args()
    if not args.workbook.is_file():
        raise SystemExit(f"Workbook not found: {args.workbook}")

    data = read_workbook(args.workbook)
    with psycopg.connect(db_url()) as connection:
        import_rows(connection, data, args.replace)
    print("Import completed.")


if __name__ == "__main__":
    main()
