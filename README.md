# AROL Customer Platform

A university project developed from the AROL × Politecnico di Torino brief.
The platform is a conversational application for industrial fleet management,
technical-manual retrieval, and assisted troubleshooting.

It combines structured fleet data with machine-specific PDF manuals while
enforcing each user's company and role boundaries.

## Highlights

- React and TypeScript frontend with authenticated chat.
- FastAPI backend with intent routing for manuals, IoT, maintenance, commercial
  data, troubleshooting, and general questions.
- PostgreSQL and pgvector for relational data and the local manual-search index.
- Local PDF chunking and embeddings: manual text is never sent to the external
  LLM.
- Server-side tenant and role enforcement for every data query.
- Structured chat results for alarms, telemetry, maintenance tickets, orders,
  quotes, and manual citations.

## Documentation

- Dataset specification and access model: [`instructions.md`](instructions.md)
- Architecture: [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md)
- Architecture decisions: [`docs/decisions.md`](docs/decisions.md)
- Technology stack: [`TECHSTACK.md`](TECHSTACK.md)
- Database setup and data-ingestion details: [`db/README.md`](db/README.md)

## Prerequisites

- Docker Desktop with Docker Compose
- A local `.env` file based on [`.env.example`](.env.example)
- The approved synthetic dataset stored locally under `data/`

## Run locally

1. Create the local configuration:

   ```bash
   cp .env.example .env
   ```

   Set the PostgreSQL settings, `AUTH_JWT_SECRET`,
   `AUTH_DEVELOPMENT_PASSWORD`, and the configured LLM credentials in `.env`.

2. Put the Excel workbook and manuals in the local `data/` directory:

   ```text
   data/
   ├── AROL_Q2_synthetic_fleet_dataset.xlsx
   └── manuals/
   ```

3. Start the application:

   ```bash
   docker compose up --build
   ```

   The frontend is available at `http://localhost:5173`; Adminer is available
   at `http://localhost:8080`.

4. On the first setup, import the workbook, initialise development passwords,
   and build the manual index:

   ```bash
   docker compose run --rm -e POSTGRES_HOST=db backend \
     sh -c "pip install -r /db/requirements.txt && python /db/scripts/import_excel.py /data/AROL_Q2_synthetic_fleet_dataset.xlsx --replace"
   docker compose run --rm backend python /db/scripts/set_development_passwords.py
   docker compose run --rm -e POSTGRES_HOST=db -v ./data:/workdata backend \
     sh -c "pip install -r /db/requirements-embeddings.txt && python /db/scripts/chunk_manuals.py /data/manuals --output /workdata/manual_chunks.jsonl && python /db/scripts/embed_manual_chunks.py /workdata/manual_chunks.jsonl"
   ```

   The first manual-index build downloads the local
   `sentence-transformers/all-MiniLM-L6-v2` model into Docker's `model_cache`
   volume. Subsequent runs reuse it.

## Access control

Users authenticate with an identifier and password. The backend issues a
short-lived JWT, then retrieves the user's company and visibility scope from
the database on every protected request.

| Visibility | Machine identity and manuals | Operational data | Commercial data |
| --- | --- | --- | --- |
| `full` | Yes | Yes | Yes |
| `technician` | Yes | Yes | No |
| `commercial` | Yes | No | Yes |

Every data access is constrained to the authenticated user's company. A request
outside the permitted role or tenant is explicitly denied; it is never
presented as an empty result.

## Manual privacy and RAG

The course manuals are restricted material and must remain in the local,
Git-ignored `data/manuals/` directory. They are not committed, pushed, or sent
to the external LLM.

The application extracts text locally, creates local embeddings, and stores
them in `manual_chunks`. For manual and troubleshooting requests, the backend
returns concise local excerpts with a file/page citation. Raw manual chunks are
not exposed in the public API response.

## Tests

The backend test suite covers authentication, tenant and role boundaries, API
contracts, routing, local manual retrieval, and the guarantee that manual and
troubleshooting flows do not call the external LLM.

```bash
docker compose run --rm backend sh -c "pip install -r requirements-dev.txt && pytest"
docker compose exec frontend npm test
```

The frontend command performs TypeScript validation and a production build.

## Repository layout

```text
backend/       FastAPI application, agents, and tests
db/            PostgreSQL schema and local data-ingestion scripts
docs/          Architecture and design decisions
frontend/      React/Vite single-page application
data/          Local synthetic dataset and manuals (ignored by Git)
```
