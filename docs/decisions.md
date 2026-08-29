# Architecture Decisions

This document collects the decisions that guide the implementation of the AROL
Customer Platform.

## 1. Python and FastAPI Backend

**Decision.** Implement the backend in Python 3.12 with FastAPI.

**Why.** Python provides mature libraries for PDF extraction, local embeddings,
database processing, and LLM integration. FastAPI provides typed REST contracts
and dependency-based authentication.

**Impact.** The frontend and backend use different languages, so their API
contracts are documented and tested explicitly.

## 2. PostgreSQL and pgvector as a Single Data Store

**Decision.** Use PostgreSQL with `pgvector` for both relational business data
and the `manual_chunks` vector index.

**Why.** A single local database keeps deployment, backup, and access
boundaries simple.

**Impact.** The project trades specialised large-scale vector-store features
for a straightforward architecture suited to the synthetic dataset.

## 3. Parameterised Data Access Instead of Free-form NL2SQL

**Decision.** Use explicit, parameterised data-access functions rather than
letting an LLM generate unrestricted SQL.

**Why.** Company and role restrictions must be deterministic and auditable.

**Impact.** Tenant and visibility filters are injected server-side. New
recurring questions may require a new query function.

## 4. Five Specialised Agents

**Decision.** Use five logical agents:

- **Manuals** — local RAG over authorised machine manuals.
- **IoT** — telemetry and alarm records.
- **Service** — maintenance tickets.
- **Orders** — quotes and orders.
- **Troubleshoot** — combines manuals, IoT, and service evidence.

**Why.** The dataset has distinct technical, operational, maintenance, and
commercial domains. Troubleshooting needs evidence from more than one of them.

**Impact.** Intent routing distinguishes direct information requests from
cross-domain diagnostic requests.

## 5. Server-side Access Control

**Decision.** Enforce company isolation and visibility roles in authentication
and SQL queries, never in an LLM prompt.

**Why.** The model and the client cannot be trusted to select their own
security scope.

**Impact.** Out-of-scope requests receive an explicit denial rather than a
misleading empty response. Every protected endpoint follows the same pattern.

## 6. Fixed Business Date

**Decision.** Use **2026-08-05** as the dataset's business date for
date-sensitive reasoning.

**Why.** It is the reference date supplied with the dataset. Using the host
clock would change the meaning of due dates and overdue items.

**Impact.** Quote validity is derived against this date and exposed by the API.
Structured-data prompts use it when interpreting date-sensitive evidence. Any
future deadline or overdue-work feature must use the same constant.

## 7. Simplified Docker Topology

**Decision.** Run `frontend`, `backend`, and `db` with Docker Compose, plus
Adminer as a development-only tool.

**Why.** The application is easier to run and present without a container for
each logical module.

**Impact.** Agents and data-access modules remain inside the backend while
their boundaries stay clear in code and documentation.

## 8. Provider-agnostic LLM Integration

**Decision.** Configure the external LLM through `LLM_BASE_URL`,
`LLM_API_KEY`, and `LLM_MODEL`.

**Why.** The project can use an OpenAI-compatible provider such as Mercury
without vendor-specific application code.

**Impact.** Changing provider is a configuration change. The LLM is used only
for suitable general and structured-data response generation.

## 9. Local PDF Manual Ingestion

**Decision.** Keep manuals in the ignored `data/manuals/` directory and extract
their text locally with `pypdf`.

**Why.** The manuals are restricted course material and must not be committed,
pushed, or uploaded to external services.

**Impact.** The pipeline preserves file and page metadata, uses section-aware
sentence chunks with overlap, and can provide verifiable citations.

## 10. Local Manual Embeddings

**Decision.** Create embeddings locally with
`sentence-transformers/all-MiniLM-L6-v2` and store them in pgvector.

**Why.** Semantic manual retrieval is needed without transmitting manual text
to an external service.

**Impact.** The first run downloads the model into Docker's `model_cache`
volume. Changing the model requires regenerating the index.

## 11. Local Authentication with bcrypt and JWT

**Decision.** Use a user ID and password login, bcrypt password hashes, and
short-lived signed JWTs for local development.

**Why.** The synthetic dataset provides users and roles but no identity
provider.

**Impact.** Secrets and development passwords remain in the ignored `.env`
file. A production system would still require HTTPS, rate limiting, secret
rotation, password-reset handling, and an identity provider.

## 12. Consistent UI Feedback and Evidence Formatting

**Decision.** Provide explicit loading, empty, access-denied, and error states.
Render manual sources as citation cards and relational results as compact
tables.

**Why.** Users must be able to distinguish a successful empty result from a
request that is loading, denied, or failed.

**Impact.** The interface presents readable English messages and avoids
exposing raw manual chunks or backend error details.
