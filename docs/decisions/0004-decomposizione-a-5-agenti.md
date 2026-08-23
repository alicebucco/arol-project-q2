# ADR 0004 — Decomposizione a 5 agenti (Manuals, IoT, Orders, Service, Troubleshoot)

## Stato
Accettata

## Contesto
Le slide AROL non sono internamente coerenti sul numero di agenti: la slide 8 ("Logical system architecture") ne mostra 4 (Manuals, IoT, Orders & Docs, Troubleshooting), la slide 9 ("AI Architecture: MCP, Gateway, Skills") ne mostra 5, aggiungendo un Service Agent dedicato ai ticket di manutenzione. Il brief lascia libertà di decomposizione ma chiede esplicitamente di motivare la scelta fatta, e in questo progetto si è scelto di aderire all'architettura AROL piuttosto che proporne una alternativa.

## Decisione
5 agenti, seguendo la slide 9 (la versione più dettagliata):

- **Manuals Agent** — RAG sui manuali PDF
- **IoT Agent** — `TelemetrySnapshots`, `Alarms`
- **Orders Agent** — `Quotes`, `QuoteRevisions`, `QuoteLines`, `Orders`, `OrderLines`
- **Service Agent** — `MaintenanceTickets`
- **Troubleshoot Agent** — agente compositivo senza tabella propria, delega a IoT + Service + Manuals

Dettaglio completo della proprietà dei dati e della motivazione in [`../architecture/03-components.md`](../architecture/03-components.md).

## Conseguenze
- `MaintenanceTickets`, che ha un foglio dedicato nel dataset, ha un agente proprietario esplicito (Service Agent) invece di essere assorbito implicitamente da IoT Agent o duplicato tra IoT e Troubleshoot.
- Il Troubleshoot Agent introduce un pattern di composizione multi-agente ("agent-as-tool") che va gestito esplicitamente nell'Orchestrator: non è un quinto accesso diretto al database, ma un consumatore degli altri quattro agenti.
- Più agenti significa più superficie di routing per l'Orchestrator: la classificazione dell'intento deve distinguere correttamente tra IoT Agent (dato grezzo) e Troubleshoot Agent (diagnosi sintetizzata) quando la domanda è ambigua.
