# ADR 0005 — Controllo accessi imposto lato server/SQL, mai delegato al modello

## Stato
Accettata

## Contesto
`istruzioni.md` definisce un modello di accesso a due livelli, entrambi obbligatori: il tenant boundary (`companyId`, mai attraversabile) e la visibilità (`full`/`technician`/`commercial`, che restringe i domini di dato raggiungibili). Vieta esplicitamente due comportamenti: rispondere con dati di un'altra azienda, e restituire un risultato vuoto come se il dato non esistesse quando in realtà l'accesso è negato.

## Decisione
Il controllo di accesso non è mai affidato al prompt o al giudizio del modello. È applicato:

1. **A monte**, nell'Auth/Session: risolve `userId` → `companyId` + `visibility` dalla sessione autenticata, non da un parametro che il modello potrebbe scegliere di passare.
2. **Nei moduli MCP**, che non espongono `companyId`/`visibility` nello schema dei tool visibile al modello.
3. **Nel Data Access Layer**, nella query SQL stessa (doppio strato, difesa in profondità).

Un accesso fuori scope restituisce un `ACCESS_DENIED` tipizzato, che l'Orchestrator trasforma in un rifiuto esplicito verso l'utente.

## Conseguenze
- Anche se un agente o un prompt venisse manipolato per "chiedere" dati fuori scope, non avrebbe comunque i parametri per farlo: lo scope non fa parte della superficie che il modello controlla.
- Ogni nuovo tool aggiunto in futuro deve seguire lo stesso pattern (scope iniettato server-side, mai passato dal modello): è un vincolo architetturale permanente, non una checklist da rifare per ogni feature.
- Richiede che ogni risposta di "nessun dato" sia distinguibile per tipo (dato assente vs. accesso negato) fino all'ultimo livello mostrato all'utente — vedi il flusso 3 in [`../architecture/04-dynamic-flows.md`](../architecture/04-dynamic-flows.md).
