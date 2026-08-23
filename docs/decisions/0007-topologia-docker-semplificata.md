# ADR 0007 — Topologia Docker semplificata a 3 servizi

## Stato
Accettata

## Contesto
Le slide AROL disegnano un MCP Gateway davanti a più server MCP distinti per dominio (Docs, Files, IoT, ERP, CRM, Search). Una topologia Docker "fedele" avrebbe un container per ciascuno di questi processi. Questo progetto è però un lavoro universitario con l'obiettivo di rendere l'architettura comprensibile ed eseguibile facilmente da chi la svilupperà, non di replicare l'infrastruttura di produzione di un'azienda reale.

## Decisione
`docker-compose.yml` definisce **3 servizi**: `frontend`, `backend`, `db`. I moduli MCP (Docs/Files/IoT/ERP/CRM/Search) e il Gateway sono implementati come **moduli Python interni al container `backend`**, non come container separati — vedi la mappatura completa in [`../architecture/00-overview.md`](../architecture/00-overview.md) e i confini logici in [`../architecture/03-components.md`](../architecture/03-components.md).

## Conseguenze
- `docker compose up` porta su l'intero sistema con un solo comando, senza dover coordinare la rete tra 6+ container MCP.
- I confini di dominio (auth, namespace dei tool, dominio di visibilità) restano visibili a livello di componente software anche se non sono processi separati: la distinzione logica non va persa solo perché è persa la distinzione fisica.
- Se in futuro servisse scalare un dominio indipendentemente dagli altri (es. il retrieval sui manuali sotto carico), la separazione in moduli interni rende relativamente semplice estrarli come processi propri senza riscrivere la logica, perché l'interfaccia tra Orchestrator e moduli MCP è già definita come confine esplicito.
