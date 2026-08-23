# ADR 0008 — Integrazione LLM generica, provider Mercury

## Stato
Accettata

## Contesto
Le prime stesure di questo progetto ipotizzavano un provider cloud "da manuale" (OpenAI o Azure OpenAI), scelto come raccomandazione di default. Il team ha poi deciso esplicitamente di **non** usare una chiave OpenAI o Anthropic, ma una chiave generica per un LLM chiamato **Mercury** (Inception Labs).

## Decisione
L'integrazione con l'LLM nel Backend è tenuta **provider-agnostica**: parla con qualunque endpoint compatibile con l'API OpenAI tramite tre variabili di configurazione (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, vedi [`../../.env.example`](../../.env.example)), non con SDK o costanti legate a un vendor specifico. Il provider attualmente configurato è **Mercury**.

## Conseguenze
- Nessun nome di provider hard-coded nel codice: cambiare LLM in futuro (es. per costo, disponibilità, o se Mercury non regge bene il tool-calling richiesto dagli agenti) significa cambiare tre variabili d'ambiente, non riscrivere l'integrazione — coerente con [`../architecture/03-components.md`](../architecture/03-components.md), dove lo stesso principio di "scope mai nel prompt, sempre in configurazione" vale anche qui.
- Mercury è un LLM meno diffuso di OpenAI/Anthropic: **va verificato in fase di implementazione** che supporti in modo affidabile il function-calling/tool use richiesto da tutti e 5 gli agenti ([ADR 0004](0004-decomposizione-a-5-agenti.md)) e dall'Orchestrator — è un rischio tecnico da validare presto con uno spike, non da dare per scontato.
- Non è ancora noto se Mercury esponga un proprio endpoint di embedding per il RAG sui manuali ([`../architecture/05-data-model.md`](../architecture/05-data-model.md)): se non lo espone, servirà un secondo endpoint di embedding compatibile OpenAI, comunque raggiungibile con lo stesso pattern di configurazione generica.
