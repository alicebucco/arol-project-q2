# Stack tecnologico

Scelte tecnologiche confermate per il progetto, una per container (vedi [`docs/architecture/02-containers.md`](docs/architecture/02-containers.md)). Le motivazioni estese sono negli ADR in [`docs/decisions/`](docs/decisions/).

| Container | Tecnologia | Motivazione sintetica |
|---|---|---|
| **Frontend SPA** | React + TypeScript, Vite | Stack richiesto per il progetto; Vite per dev server veloce e build semplice |
| **Backend API** | Python 3.12, FastAPI | Ecosistema più maturo per agenti AI/RAG (orchestrazione a grafo, SDK MCP, pandas/openpyxl), coerente con lo stack suggerito da AROL — [ADR 0001](docs/decisions/0001-python-fastapi-backend.md) |
| **Database** | PostgreSQL 16 + estensione `pgvector` | Un solo motore per dati relazionali ed embedding dei manuali, meno infrastruttura da gestire — [ADR 0002](docs/decisions/0002-postgres-pgvector-unico-motore.md) |
| **LLM** | Mercury (Inception Labs), via API generica compatibile OpenAI | Scelta del team; integrazione tenuta provider-agnostica (`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`) per poter cambiare provider senza riscrivere il codice — [ADR 0008](docs/decisions/0008-provider-llm-generico-mercury.md) |
| **Embedding** (per il RAG sui manuali) | Da definire in fase di implementazione, stesso pattern di integrazione generica | Mercury è valutato principalmente come LLM di chat/completion: se non espone un endpoint di embedding, se ne userà uno separato compatibile OpenAI |
| **Orchestrazione container** | Docker Compose, 3 servizi logici + Adminer come tool di sviluppo | Un solo comando (`docker compose up`) per l'intero sistema, senza container per ogni server MCP — [ADR 0007](docs/decisions/0007-topologia-docker-semplificata.md) |

Il backend usa un piccolo `backend/Dockerfile`, derivato da `python:3.12-slim`, per installare le dipendenze in un layer Docker riutilizzabile. Il codice sorgente resta montato come bind mount durante lo sviluppo, quindi una modifica al codice non reinstalla lo stack ML. Il frontend continua a usare l'immagine ufficiale `node:20-alpine` — vedi [`docker-compose.yml`](docker-compose.yml).
