# Technology Stack

| Area | Technology | Role in the project |
| --- | --- | --- |
| Frontend | React, TypeScript, Vite | Responsive single-page application and authenticated chat interface. |
| Backend | Python 3.12, FastAPI | REST API, authentication, orchestration, role enforcement, and data access. |
| Database | PostgreSQL 16 with `pgvector` | Stores the relational dataset and local vector index for manual retrieval. |
| LLM | Mercury through an OpenAI-compatible API | Generates English responses only when no manual content must be processed externally. |
| Manual embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Runs locally to index and retrieve restricted PDF manual content. |
| Containers | Docker Compose | Starts frontend, backend, PostgreSQL, and Adminer with one command. |
| Tests | pytest, TypeScript compiler, Vite build | Verifies backend behaviour and frontend type/build integrity. |

The backend Docker image is based on `python:3.12-slim`. During development,
source code is mounted into the container, while the local embedding model is
cached in Docker's `model_cache` volume. The frontend uses the official
`node:20-alpine` image. See [`docker-compose.yml`](docker-compose.yml) and the
[architecture documentation](docs/architecture/00-overview.md) for details.
