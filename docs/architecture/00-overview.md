# Architettura — Indice

Questo documento è il punto d'ingresso alla documentazione architetturale della **AROL Customer Platform**, un'app conversazionale ad agenti AI per la gestione della flotta industriale e il troubleshooting autonomo (progetto universitario, sviluppato a partire dal brief in [`../../istruzioni.md`](../../istruzioni.md) e dalla presentazione [`../../AROL-presentation-project-Q2.pdf`](../../AROL-presentation-project-Q2.pdf)).

La documentazione segue il **modello C4** (Context → Container → Component), integrato con diagrammi dinamici per i flussi chiave e un diagramma dei dati:

| Documento | Livello C4 | Contenuto |
|---|---|---|
| [`01-context.md`](01-context.md) | 1 — System Context | Chi usa il sistema, quali sistemi esterni tocca |
| [`02-containers.md`](02-containers.md) | 2 — Container | I processi/servizi deployabili e come comunicano |
| [`03-components.md`](03-components.md) | 3 — Component | Come è fatto internamente il container Backend (orchestrator, agenti, moduli MCP) |
| [`04-dynamic-flows.md`](04-dynamic-flows.md) | Dinamico (supplementare) | Sequence diagram dei flussi chiave: QR entry, troubleshooting cross-agente, rifiuto per accesso negato |
| [`05-data-model.md`](05-data-model.md) | Dati (supplementare) | Schema entità-relazione e semantica del dataset |

Le decisioni di design con relative motivazioni sono raccolte separatamente come Architecture Decision Record in [`../decisions/`](../decisions/README.md).

**Cosa non è (ancora) coperto, e perché:** il modello C4 prevede un quarto livello, Code, e opzionalmente un diagramma di Deployment. Il Livello 4 è omesso perché non esiste ancora codice da scomporre in classi/funzioni — verrà naturale scriverlo quando `backend/` e `frontend/` esisteranno. Un diagramma di Deployment dedicato è stato invece giudicato ridondante rispetto a [`02-containers.md`](02-containers.md): con la topologia semplificata a 3 servizi Docker ([ADR 0007](../decisions/0007-topologia-docker-semplificata.md)) il diagramma dei container coincide già con quello di deployment (un solo host, un container per servizio).

## Tabella di tracciabilità: slide AROL → questa implementazione

Il brief lascia esplicitamente aperta la decomposizione in agenti ("*the number of agents, their responsibilities, and the way work is divided between them are design decisions left to each team [...] You are expected to justify the design you choose*"), ma per questo progetto si è scelto di **aderire all'architettura suggerita da AROL** (slide 8 "Logical system architecture" e slide 9 "AI Architecture: MCP, Gateway, Skills") anziché proporne una alternativa. Questa tabella rende quella scelta verificabile riga per riga: ogni box delle due slide è o un componente che costruiamo, o una riga con una motivazione esplicita di come viene mappato/semplificato in questo progetto universitario.

| Box slide (8/9) | Implementazione in questo progetto | Motivazione |
|---|---|---|
| End User · Mobile (QR scan) · Web Portal | Route Frontend `/machines/:serialOrId` | Il QR incapsula l'URL della macchina, come suggerito in `istruzioni.md` |
| Web/Mobile Frontend · Chatbot UI | Container **Frontend SPA** (React + TypeScript) | Vedi [`02-containers.md`](02-containers.md) |
| Backend API · Auth · Session | Container **Backend API** (FastAPI), modulo Auth/Session | Vedi [`03-components.md`](03-components.md) |
| AI Orchestrator · Intent routing · Planning · Conversation memory | Componente **Orchestrator** dentro il Backend | Vedi [`03-components.md`](03-components.md) |
| Agent · Manuals | **Manuals Agent** — RAG sui manuali PDF | 1:1 |
| Agent · IoT | **IoT Agent** — query su `TelemetrySnapshots`, `Alarms` | 1:1 |
| Agent · Orders & Docs (slide 8) / Orders Agent (slide 9, 11) | **Orders Agent** — query su `Quotes`, `QuoteRevisions`, `QuoteLines`, `Orders`, `OrderLines` | "Orders & Docs" di slide 8 è trattato come formulazione meno rifinita dello stesso agente di slide 9/11: i "docs" sono gli allegati contrattuali della quotazione (slide 5, "Contractual documents"), non i manuali (già coperti da Manuals Agent) |
| Agent · Troubleshooting | **Troubleshoot Agent** — agente compositivo, nessuna tabella propria | Vedi "Discrepanza conteggio agenti" in [`03-components.md`](03-components.md) |
| Service Agent · Tickets & support (solo slide 9) | **Service Agent** — query su `MaintenanceTickets` | `MaintenanceTickets` è un foglio reale del dataset: implementiamo 5 agenti seguendo slide 9, non 4 come slide 8 |
| MCP Gateway · Auth · Rate limiting · Routing · Observability | Livello di enforcement nel Backend (auth, injection dello scope utente, logging) davanti ai moduli MCP | In questo progetto universitario il Gateway non è un processo separato ma un livello logico interno al Backend — vedi ADR [`0007-topologia-docker-semplificata.md`](../decisions/0007-topologia-docker-semplificata.md) |
| Docs MCP | Modulo `docs-mcp` — retrieval semantico sui chunk dei manuali (pgvector) | Skill RAG |
| Files MCP | Modulo `files-mcp` — serve i PDF grezzi/pagina per il rendering della citazione lato Frontend | Distinto da Docs MCP: uno fa retrieval semantico, l'altro serve i byte per mostrare la fonte |
| IoT MCP | Modulo `iot-mcp` — tool su `TelemetrySnapshots`/`Alarms` (namespace `iot.*`) **e** su `MaintenanceTickets` (namespace `service.*`) | `istruzioni.md` raggruppa Telemetry+Alarms+MaintenanceTickets sotto lo stesso dominio di visibilità ("Operational data"): un solo confine di accesso, due namespace di tool per mantenere la distinzione IoT Agent / Service Agent |
| ERP MCP | Namespace `erp.*` dentro il modulo `commercial-mcp`: `Orders`, `OrderLines` | Vedi riga sotto |
| CRM MCP | Namespace `crm.*` dentro il modulo `commercial-mcp`: `Quotes`, `QuoteRevisions`, `QuoteLines` | ERP e CRM sono sistemi distinti in un'azienda reale; nel dataset sintetico condividono lo stesso schema Postgres. Un solo modulo `commercial-mcp`, due namespace per preservare l'interfaccia che la slide disegna |
| Search MCP | Modulo `search-mcp` — full-text search Postgres su chunk manuali + record commerciali | Skill Search, fallback/complemento del RAG semantico e lookup su testo libero nei dati strutturati |
| Skill · RAG | Retrieval semantico via `pgvector`, usato da Manuals Agent | — |
| Skill · Search | Full-text search Postgres, usata da più agenti | — |
| Skill · Summarize | Funzione helper con prompt dedicato (non un modulo a sé) per condensare cronologie revisioni o sezioni lunghe dei manuali | Riusata da Orders Agent e Manuals Agent |
| Skill · Diagnose | Analisi statistica (soglie/trend su `productionRateBph`, `uptimePercentage`) + interpretazione LLM | Tool esposto a IoT Agent e Troubleshoot Agent |
| Skill · Notify | **Non implementata** | Il dataset non fornisce un sistema di notifica reale (email/SMS/push): implementarla simulerebbe un'infrastruttura inesistente. Fuori perimetro |
| Skill · Report | Formattazione strutturata (markdown/tabella) dell'output di Orders Agent | Semplificazione dichiarata, non un vero export PDF |

## Cosa è fuori perimetro in questo repository

Questo repository contiene **solo documentazione architetturale, infrastruttura Docker e il dataset fornito dal corso**, non l'applicazione. Non ci sono ancora `backend/` né `frontend/`: la loro struttura interna attesa è descritta in [`02-containers.md`](02-containers.md) e [`03-components.md`](03-components.md), e sarà lo sviluppatore del progetto a popolarle.

Il dataset reale è in `data/` (`AROL_Q2_synthetic_fleet_dataset.xlsx`, `data/manuals/`); lo schema in [`05-data-model.md`](05-data-model.md) è stato verificato contro i nomi reali di fogli e colonne. **Nota importante:** i manuali PDF portano una notice a pagina 2 che vieta la pubblicazione su repository di codice pubblici o privati — vedi l'avviso in [`../../README.md`](../../README.md).
