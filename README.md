# AROL Customer Platform

A university project developed from the AROL × Politecnico di Torino brief.
The platform is a conversational application for industrial fleet management,
technical-manual retrieval, and assisted troubleshooting.

It combines structured fleet data with machine-specific PDF manuals while
enforcing each user's company and role boundaries.

## Highlights

- React and TypeScript frontend with authenticated chat.
- FastAPI backend with LLM-planned, backend-validated orchestration across
  manuals, IoT, maintenance, commercial data, and general questions.
- PostgreSQL and pgvector for relational data and the local manual-search index.
- Local PDF chunking and embeddings: PDFs, raw chunks, PostgreSQL, and the
  vector index never leave the backend. Raw manual chunks are not passed to the
  final answer composer; for multi-agent answers, only backend-validated manual
  sentences are combined with IoT, Service, and Orders evidence.
- Server-side tenant and role enforcement for every data query.
- Structured chat results for alarms, telemetry, maintenance tickets, orders,
  quotes, and manual citations.

## Documentation

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

   With the default Docker Compose port mappings, the frontend is available at
   `http://localhost:5173`, the backend API at `http://localhost:8000`, and
   Adminer at `http://localhost:8080`. Set `FRONTEND_PORT` to use a different
   host port for the frontend. Interactive API documentation is available at
   `http://localhost:8000/docs`.

   The backend root intentionally does not serve a web page: `GET /` returns
   `404 {"detail":"Not Found"}`. Use the frontend or the API routes instead.

4. On the first setup, import the workbook, initialise development passwords,
   build the manual index, and index the planner capabilities:

   ```bash
   docker compose run --rm -e POSTGRES_HOST=db backend \
     sh -c "pip install -r /db/requirements.txt && python /db/scripts/import_excel.py /data/AROL_Q2_synthetic_fleet_dataset.xlsx --replace"
   docker compose run --rm backend python /db/scripts/set_development_passwords.py
   docker compose run --rm -e POSTGRES_HOST=db -v ./data:/workdata backend \
     sh -c "pip install -r /db/requirements-embeddings.txt && python /db/scripts/chunk_manuals.py /data/manuals --output /workdata/manual_chunks.jsonl && python /db/scripts/embed_manual_chunks.py /workdata/manual_chunks.jsonl"
   docker compose exec backend python /db/scripts/index_operation_capabilities.py
   ```

   The first manual-index build downloads the local
   `sentence-transformers/all-MiniLM-L6-v2` model into Docker's `model_cache`
   volume. Subsequent runs reuse it. Re-run the final command whenever the
   registered planner operations change.

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

## Manual privacy, RAG, and LLM evidence

The course manuals are restricted material and must remain in the local,
Git-ignored `data/manuals/` directory. PDF files are not committed, pushed, or
sent to the external LLM. The LLM never has direct access to PostgreSQL, the
`manual_chunks` table, the embedding model, or the vector index.

The application extracts text locally, creates local embeddings, and stores
them in `manual_chunks`. An authorised manual search returns concise,
relevance-ranked excerpts with file/page citations for the user interface.

For a chat answer, raw manual chunks remain private backend evidence. The LLM
first selects sentence indexes from authorised chunks, and the backend validates
those indexes. The final composer receives only the validated manual sentences,
together with any relevant IoT, Service, or Orders evidence. If manual-sentence
selection fails, non-manual evidence remains available for composition. Raw
chunks are not exposed in the public API response and are never sent wholesale
to the provider.

The LLM first proposes a typed plan that selects only registered agent
operations. The backend validates that plan, applies all tenant and role checks,
retrieves evidence, and invokes the composer. It can combine several evidence
agents for a diagnostic question; diagnostics are an orchestrated workflow, not
a separate agent with broader database access.

## Tests

The backend test suite covers authentication, tenant and role boundaries, API
contracts, structured plan validation, local manual retrieval, evidence
minimisation, and grounded composition. On Windows, create the local backend
virtual environment once and run the suite from the repository root:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

The local backend suite skips the isolated PostgreSQL integration tests below.
Before a live orchestrator evaluation, run the required local checks:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_orchestrator.py backend/tests/test_evaluate_orchestrator.py backend/tests/test_planner.py backend/tests/test_api.py backend/tests/test_llm.py
```

For a frontend type check and production build, run:

```bash
cd frontend
npm test
```

### Isolated PostgreSQL integration tests

The API integration tests use a disposable PostgreSQL database on port `55432`.
They apply the same schema migrations as the development database, create a
small synthetic dataset, verify a real bcrypt login and JWT-protected API
requests, and never read the local Excel file or manuals.

```bash
docker compose -f docker-compose.integration.yml up -d --wait
docker compose -f docker-compose.integration.yml run --rm integration-backend sh -c "pip install -r requirements-dev.txt && pytest tests/integration"
docker compose -f docker-compose.integration.yml down
```

### Frontend end-to-end tests

```bash
cd frontend
npm run test:e2e
```

Playwright mocks backend responses, so browser tests do not require project
credentials, the production database, or non-publishable manuals.

### Local RAG evaluation

Create a local golden dataset under `data/evaluations/` (which is ignored by
Git), then run the evaluator against the locally indexed manuals. Always use a
new, descriptive report name:

```powershell
docker compose --profile tools run --rm rag-evaluator python scripts/evaluate_rag.py --output /data/evaluations/rag-manual-agent-evaluation-20260910-120000.json
```

The report contains file Recall@K, mean reciprocal rank, keyword coverage, exact
page Recall@K, and page Recall@K within the configured tolerance. It contains
citations and metrics only, never raw manual text. Keyword coverage measures
expected terms found in retrieved chunks; it is not a semantic correctness score
for a generated answer.

The latest local 16-case RAG evaluation achieved file Recall@3 of 100%, MRR of
1.000, exact page Recall@3 of 75%, page Recall@3 within +/-2 pages of 93.8%,
and mean keyword coverage of 0.714.

### Local orchestrator evaluation

`data/evaluations/orchestrator_questions.yaml` is an ignored local, 20-case
synthetic suite for evaluating the complete authorised orchestrator path against
an OpenAI-compatible LLM. It records deterministic checks for selected agents
and manual citations, together with expected facts and safety constraints for
case-by-case human review. It does not store the API key.

```powershell
docker compose --profile tools run --rm rag-evaluator python scripts/evaluate_orchestrator.py --output /data/evaluations/orchestrator-groq-20260910-120000.json --markdown-output /data/evaluations/orchestrator-groq-20260910-120000.md
```

Set `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` in the root `.env` before
each provider run. The report records the configured provider and model,
planner action, planned operations, executed operations, public manual
citations, and chatbot response for every case. For unstable providers, run
sequential blocks of up to five cases by repeating `--case`. Use a new,
descriptive report name for every run and use `--repetitions` when measuring
variation from the same model.

A failed request must be classified carefully: provider failure, planning
failure, execution failure, incomplete-evidence synthesis, and semantic error
are distinct outcomes. The current API error handling can normalise provider
failures into a generic error, so the original provider status code or message
may not be preserved in the report.

## Evaluation artefacts and final delivery

The public repository intentionally excludes `data/`, `.env`, the Excel
workbook, and the PDF manuals. These files contain authorised local course
material or credentials and must not be committed or published.

The project uses two homemade synthetic evaluation suites derived from the
authorised local course material:

- a 16-case RAG retrieval suite;
- a 20-case end-to-end orchestrator suite.

They are project-specific synthetic benchmarks, not publicly available
benchmarks. No directly applicable public benchmark is claimed for the
proprietary AROL machine, commercial, telemetry, and manual domain.

For a delivery archive, include only artefacts that the course rules permit to
be redistributed: the evaluation datasets, selected time-stamped reports, and a
short benchmark summary. Do not include `.env`, PDF manuals, the Excel workbook,
or any report containing restricted manual text or sensitive commercial data.

## Repository layout

```text
backend/       FastAPI entry point, API routes, agents, and tests
db/            PostgreSQL schema and local data-ingestion scripts
frontend/      React/Vite single-page application
data/          Local synthetic dataset and manuals (ignored by Git)
```
