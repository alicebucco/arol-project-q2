# AROL Customer Platform

University project: a conversational multi-agent AI platform for industrial
fleet management and autonomous troubleshooting, based on the AROL × Politecnico
di Torino brief.

> **New to backend, frontend, databases, Docker, or AI?** Start with
> [`ALICE.md`](ALICE.md), which explains the project from the beginning.

- Dataset specification and access model: [`istruzioni.md`](istruzioni.md)
- Customer presentation: [`AROL-presentation-project-Q2.pdf`](AROL-presentation-project-Q2.pdf)
- Architecture documentation (C4 + Mermaid): [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md)
- Architecture Decision Records: [`docs/decisions/`](docs/decisions/README.md)
- Technology stack: [`TECHSTACK.md`](TECHSTACK.md)

## Repository contents

This repository contains the project documentation, Docker infrastructure, and
the PostgreSQL schema/import tooling. The application itself is still to be
implemented: the expected backend and frontend structure is described in
[`docs/architecture/02-containers.md`](docs/architecture/02-containers.md) and
[`docs/architecture/03-components.md`](docs/architecture/03-components.md).

## Local database setup

The backend uses Python 3.12 both locally and in Docker. On macOS, create the
local environment with:

```bash
python3.12 -m venv venv
venv/bin/pip install -r backend/requirements.txt
```

Create a local `.env` file (it is ignored by Git) with the PostgreSQL settings:

You can start from [`.env.example`](.env.example). It also documents the
Docker hostname (`db`) and the Mercury-compatible LLM settings.

```dotenv
POSTGRES_USER=arol
POSTGRES_PASSWORD=choose_a_local_password
POSTGRES_DB=arol
```

Start PostgreSQL and Adminer:

```bash
docker compose up -d db adminer
```

Adminer is available at `http://localhost:8080`. Connect with server `db` and
the credentials from `.env`.

Once the Excel workbook is available locally, import it with:

```bash
docker compose run --rm -e POSTGRES_HOST=db backend \
  sh -c "pip install -r /db/requirements.txt && python /db/scripts/import_excel.py /data/AROL_Q2_synthetic_fleet_dataset.xlsx --replace"
```

See [`db/README.md`](db/README.md) for details about the schema and importer.

## Authentication and access control (development)

The current session adapter authenticates requests with the `X-User-Id`
header and resolves that user against the `users` table. For example:

```bash
curl -H "X-User-Id: USR-001" http://localhost:8000/machines/lookup/15610
```

Every query is constrained to the authenticated user's `company_id`. The
dataset visibility matrix is enforced server-side: `full` can access all
domains, `technician` can access operational data, and `commercial` can access
quotes/orders. A missing identity returns `401`; an authenticated request
outside its tenant or visibility scope returns `403 {"detail":"Access denied."}`.
This header-based adapter is intentionally replaceable by JWT/session
verification when a real identity provider is connected.

The first data-aware agent is the IoT Agent:

```text
GET /machines/{machine_id}/alarms?limit=20
GET /machines/{machine_id}/telemetry?limit=24
```

Both endpoints require `X-User-Id`, restrict access to the user's company, and
allow only `full` or `technician` users because they expose operational data.

The Service Agent uses the same access boundary for maintenance history:

```text
GET /machines/{machine_id}/maintenance-tickets?limit=20
```

The Manuals Agent performs local semantic search only in the PDF manual of the
authorised physical machine. It returns chunk text plus a structured citation:

```text
GET /machines/{machine_id}/manuals/search?query=low%20air%20pressure&limit=5
```

The endpoint requires `X-User-Id`; it permits `full`, `technician`, and
`commercial` users, while the query itself is always constrained to the
requested machine and its company.

The Orders Agent exposes commercial data only for `full` and `commercial`
users. The company scope is taken from the authenticated session:

```text
GET /orders?limit=20
GET /quotes?limit=20
```

## Dataset: local only and hidden from Git

The synthetic dataset must be placed locally in `data/`:

```text
data/
├── AROL_GENERAL_CATALOGUE_11.0_EN_20230215.pdf
├── AROL_Q2_synthetic_fleet_dataset.xlsx
└── manuals/
```

`data/` is deliberately listed in [`.gitignore`](.gitignore). It is therefore
**not tracked, committed, pushed, or visible on GitHub**, including to repository
collaborators. Each collaborator must obtain the dataset through an approved
course/AROL channel and copy it into their own local `data/` directory.

The general catalogue is useful for future product-level retrieval. It is not a
substitute for the machine-specific manuals in `data/manuals/`: troubleshooting,
safety, configuration, and maintenance guidance must use the manual matched to
the physical machine's `serialNumber`.

> **Restricted AROL course material.** The manuals in `data/manuals/` state
> that they must not be uploaded to any website or public or private code
> repository, and must be deleted after the course. Do not use Git, Git LFS, or
> any Git repository to distribute this directory. See the disclaimer in
> [`istruzioni.md`](istruzioni.md) for the applicable project rules.
