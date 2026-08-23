# ADR 0002 — Postgres + pgvector come unico motore di persistenza

## Stato
Accettata

## Contesto
Il progetto deve persistere due tipi di dato molto diversi: dati relazionali strutturati (le tabelle del dataset AROL: Companies, Machines, Quotes, Telemetry, ...) e vettori di embedding per il RAG sui manuali PDF. Serviva decidere se usare un solo motore o due sistemi separati (un DB relazionale + un vector store dedicato come Chroma/Qdrant).

## Decisione
Un solo motore: **PostgreSQL con l'estensione `pgvector`**, sia per i dati relazionali sia per gli embedding dei chunk dei manuali (tabella `manual_chunks`, vedi [`../architecture/05-data-model.md`](../architecture/05-data-model.md)).

## Conseguenze
- Meno infrastruttura da gestire in un progetto universitario: un solo container DB in `docker-compose.yml`, un solo backup, una sola connessione da mantenere nel Data Access Layer.
- Consistenza transazionale unica tra dati di business e dati di RAG (ad es. se una macchina viene rimossa non serve sincronizzare due sistemi).
- Rispetto a un vector store dedicato si rinuncia ad alcune ottimizzazioni specifiche di ricerca vettoriale su larga scala, non rilevanti alla scala di un dataset sintetico didattico.
