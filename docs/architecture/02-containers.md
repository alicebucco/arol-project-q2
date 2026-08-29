# C4 — Level 2: Containers

## Purpose

The platform is deployed locally through Docker Compose. Its runtime consists
of a frontend, a backend API, and a PostgreSQL database; Adminer is included as
a development-only database browser.

## Containers

| Container | Technology | Responsibility | Docker service |
| --- | --- | --- | --- |
| **Frontend SPA** | React, TypeScript, Vite | Login, chat interface, structured result tables, and manual-source cards. | `frontend` (port 5173) |
| **Backend API** | Python, FastAPI | Authentication, routing, agents, access checks, data retrieval, and response formatting. | `backend` (port 8000) |
| **Database** | PostgreSQL with `pgvector` | Relational dataset, password hashes, and local manual chunks with embeddings. | `db` (port 5432) |
| **Adminer** | Adminer | Development-only browser interface for PostgreSQL. | `adminer` (port 8080) |

The backend is the only service that reaches the external LLM API. Local
embedding generation uses the cached sentence-transformer model and does not
transmit manual content externally.

## Diagram

```mermaid
flowchart TB
    classDef person fill:#08427b,stroke:#052e56,color:#ffffff
    classDef container fill:#438dd5,stroke:#2e6295,color:#ffffff
    classDef db fill:#666666,stroke:#444444,color:#ffffff
    classDef external fill:#999999,stroke:#6b6b6b,color:#ffffff

    User["<b>Customer user</b>"]:::person

    subgraph Platform["AROL Customer Platform — Docker Compose"]
        FE["<b>Frontend SPA</b><br/>React + TypeScript + Vite<br/>Login, chat, citations, tables"]:::container
        BE["<b>Backend API</b><br/>Python + FastAPI<br/>Auth, orchestration, agents"]:::container
        DB[("<b>Database</b><br/>PostgreSQL + pgvector<br/>Business data + local RAG index")]:::db
        Adminer["<b>Adminer</b><br/>Development tool"]:::container
    end

    LLM["<b>LLM provider</b><br/>External API"]:::external

    User -->|"HTTPS"| FE
    FE -->|"REST / JSON"| BE
    BE -->|"SQL"| DB
    Adminer -.->|"Development only"| DB
    BE -->|"HTTPS; no manual text"| LLM
```
