# Technology Stack

| Area | Technology | Role in the project |
| --- | --- | --- |
| Frontend | React, TypeScript, Vite | Responsive single-page application and authenticated chat interface. |
| Backend | Python 3.12, FastAPI | REST API, authentication, orchestration, role enforcement, and data access. |
| Database | PostgreSQL 16 with `pgvector` | Stores the relational dataset and local vector index for manual retrieval. |
| Orchestration | Custom Python orchestration layer | Generates LLM-assisted plans, validates registered operations in the backend, executes specialised agents, and composes grounded responses. |
| LLM | Groq via an OpenAI-compatible API (default model: `openai/gpt-oss-20b`) | Produces validated orchestration plans and grounded English responses from bounded, authorised evidence. |
| Manual embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Runs locally to index and retrieve restricted PDF manual content. |
| Containers | Docker Compose | Starts frontend, backend, PostgreSQL, and Adminer with one command. |
| Tests | pytest, TypeScript compiler, Vite build, Playwright | Verifies backend behaviour, frontend type/build integrity, and browser end-to-end flows. |

The backend Docker image is based on `python:3.12-slim`. During development,
source code is mounted into the container, while the local embedding model is
cached in Docker's `model_cache` volume. The frontend uses the official
`node:20-alpine` image. See [`docker-compose.yml`](docker-compose.yml) for
the service configuration.
