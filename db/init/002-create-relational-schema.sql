-- Relational schema for the AROL dataset.
-- Names use snake_case; db/scripts/import_excel.py automatically maps
-- camelCase workbook headers.

CREATE TABLE companies (
    company_id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    country TEXT NOT NULL,
    city TEXT NOT NULL,
    sector TEXT NOT NULL,
    currency TEXT NOT NULL,
    locale TEXT NOT NULL,
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(company_id),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    job_title TEXT NOT NULL,
    visibility TEXT NOT NULL CHECK (visibility IN ('full', 'technician', 'commercial')),
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE machine_models (
    model_id TEXT PRIMARY KEY,
    model_code TEXT NOT NULL,
    description TEXT,
    primitive_diameter NUMERIC,
    nominal_heads INTEGER,
    container_type TEXT,
    cap_type TEXT,
    industry_segment TEXT,
    notes TEXT,
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE machines (
    machine_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(company_id),
    model_id TEXT NOT NULL REFERENCES machine_models(model_id),
    serial_number TEXT NOT NULL UNIQUE,
    delivery_date DATE,
    plant_location TEXT,
    configuration_profile TEXT,
    plc_family TEXT CHECK (plc_family IN ('SIEMENS-SIMATIC-S7', 'LINE-PLC-INTEGRATED', 'HARDWIRED-CONTROL-PANEL')),
    software_version TEXT,
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE quotes (
    quote_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(company_id),
    valid_until DATE,
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE quote_revisions (
    quote_revision_id TEXT PRIMARY KEY,
    quote_id TEXT NOT NULL REFERENCES quotes(quote_id),
    revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
    revision_status TEXT NOT NULL CHECK (revision_status IN ('Draft', 'Submitted', 'Superseded', 'Approved', 'Rejected', 'Expired')),
    discount_rate NUMERIC,
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (quote_id, revision_number)
);

CREATE TABLE quote_lines (
    quote_line_id TEXT PRIMARY KEY,
    quote_revision_id TEXT NOT NULL REFERENCES quote_revisions(quote_revision_id),
    machine_id TEXT REFERENCES machines(machine_id),
    price NUMERIC,
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    quote_id TEXT NOT NULL REFERENCES quotes(quote_id),
    company_id TEXT NOT NULL REFERENCES companies(company_id),
    order_status TEXT NOT NULL CHECK (order_status IN ('Confirmed', 'In production', 'Delivered', 'Closed')),
    shipment_status TEXT NOT NULL CHECK (shipment_status IN ('In production', 'Ready for shipment', 'Delivered', 'Installed')),
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE order_lines (
    order_line_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    fulfillment_status TEXT NOT NULL CHECK (fulfillment_status IN ('Manufacturing', 'Ready for shipment', 'Delivered')),
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE telemetry_snapshots (
    telemetry_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL REFERENCES machines(machine_id),
    timestamp TIMESTAMPTZ NOT NULL,
    operational_status TEXT NOT NULL CHECK (operational_status IN ('Running', 'Alarm', 'Idle', 'Stopped', 'Maintenance', 'Size change')),
    production_rate_bph NUMERIC NOT NULL,
    uptime_percentage NUMERIC NOT NULL CHECK (uptime_percentage BETWEEN 0 AND 100),
    alarm_count INTEGER NOT NULL CHECK (alarm_count >= 0),
    temperature_c NUMERIC,
    energy_kwh NUMERIC,
    health_note TEXT,
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE alarms (
    alarm_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL REFERENCES machines(machine_id),
    timestamp TIMESTAMPTZ NOT NULL,
    alarm_code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('Critical', 'High', 'Medium', 'Low')),
    alarm_status TEXT NOT NULL CHECK (alarm_status IN ('Open', 'Acknowledged', 'Resolved')),
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE maintenance_tickets (
    ticket_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL REFERENCES machines(machine_id),
    alarm_id TEXT REFERENCES alarms(alarm_id),
    ticket_type TEXT NOT NULL CHECK (ticket_type IN ('Remote troubleshooting', 'On-site service', 'Spare parts request', 'Scheduled maintenance', 'Overhaul', 'Size change assistance')),
    ticket_status TEXT NOT NULL CHECK (ticket_status IN ('Open', 'In progress', 'Waiting for parts', 'Resolved', 'Closed')),
    priority TEXT NOT NULL CHECK (priority IN ('Critical', 'High', 'Medium', 'Low')),
    created_date DATE NOT NULL,
    owner_role TEXT NOT NULL CHECK (owner_role IN ('Line Operator', 'Maintenance Man', 'Plant Maintenance Manager', 'AROL Technical Service')),
    source_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_users_company_id ON users(company_id);
CREATE INDEX idx_machines_company_id ON machines(company_id);
CREATE INDEX idx_telemetry_machine_timestamp ON telemetry_snapshots(machine_id, timestamp DESC);
CREATE INDEX idx_alarms_machine_timestamp ON alarms(machine_id, timestamp DESC);
CREATE INDEX idx_tickets_machine_created_date ON maintenance_tickets(machine_id, created_date DESC);
CREATE INDEX idx_quotes_company_id ON quotes(company_id);
CREATE INDEX idx_orders_company_id ON orders(company_id);
