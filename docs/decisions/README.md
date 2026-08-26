# Architecture Decision Records

Elenco delle decisioni di design motivate per questo progetto, in formato ADR breve (contesto/decisione/conseguenze). Referenziate dai documenti di architettura in [`../architecture/`](../architecture/).

| ADR | Decisione |
|---|---|
| [0001](0001-python-fastapi-backend.md) | Backend in Python + FastAPI |
| [0002](0002-postgres-pgvector-unico-motore.md) | Postgres + pgvector come unico motore di persistenza |
| [0003](0003-tool-parametrici-non-nl2sql.md) | Tool parametrici fissi invece di NL2SQL libero |
| [0004](0004-decomposizione-a-5-agenti.md) | Decomposizione a 5 agenti (Manuals, IoT, Orders, Service, Troubleshoot) |
| [0005](0005-controllo-accessi-lato-server.md) | Controllo accessi imposto lato server/SQL, mai delegato al modello |
| [0006](0006-orologio-di-business-congelato.md) | Orologio di business congelato al 2026-08-05 |
| [0007](0007-topologia-docker-semplificata.md) | Topologia Docker semplificata a 3 servizi |
| [0008](0008-provider-llm-generico-mercury.md) | Integrazione LLM generica, provider Mercury |
| [0009](0009-ingestion-manuali-pdf-locali.md) | Ingestion locale dei manuali PDF con pypdf |
| [0010](0010-embedding-locali-manuali.md) | Embedding locali con all-MiniLM-L6-v2 |
