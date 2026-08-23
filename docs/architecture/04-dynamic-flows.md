# Diagrammi dinamici — flussi chiave

Diagrammi di sequenza per i tre scenari che più caratterizzano questa architettura: ingresso da QR, ragionamento multi-agente, e rifiuto esplicito per accesso fuori scope. Fanno riferimento ai componenti definiti in [`03-components.md`](03-components.md).

## 1. Ingresso da QR

La scansione del QR è una superficie di controllo accessi (contratto trasversale #5 in [`03-components.md`](03-components.md)): una macchina di un'altra azienda deve produrre un rifiuto esplicito, non uno scoping-e-risposta silenzioso.

```mermaid
sequenceDiagram
    actor U as Utente
    participant FE as Frontend SPA
    participant Auth as Auth/Session
    participant DAL as Data Access Layer
    participant DB as Postgres

    U->>FE: Scansiona QR → apre /machines/17478
    FE->>Auth: GET /machines/17478 (JWT utente)
    Auth->>DAL: getMachine(serialNumber=17478, companyId=<dalla sessione>)
    DAL->>DB: SELECT ... WHERE serialNumber = ? AND companyId = ?
    alt macchina appartiene alla company dell'utente
        DB-->>DAL: riga macchina
        DAL-->>Auth: machineId, modello, config
        Auth-->>FE: sessione chat scoped su machineId
        FE-->>U: chat aperta, contesto macchina precompilato
    else macchina di un'altra company o inesistente
        DB-->>DAL: nessuna riga
        DAL-->>Auth: NOT_FOUND_OR_FORBIDDEN
        Auth-->>FE: 403 esplicito
        FE-->>U: "Questa macchina non è associata al tuo account" (mai silenzio o pagina vuota)
    end
```

## 2. Domanda cross-dominio (troubleshooting)

Esempio: *"Perché la macchina 17478 continua ad allarmare?"* — richiede di comporre 3 agenti, non uno solo.

```mermaid
sequenceDiagram
    actor U as Utente
    participant Orch as Orchestrator
    participant Trouble as Troubleshoot Agent
    participant IoT as IoT Agent
    participant Svc as Service Agent
    participant Man as Manuals Agent

    U->>Orch: "Perché la macchina 17478 continua ad allarmare?"
    Orch->>Orch: intent routing → dominio troubleshooting
    Orch->>Trouble: delega con contesto (machineId, companyId, visibility)

    Trouble->>IoT: getRecentAlarms(machineId)
    IoT-->>Trouble: [{alarmCode: AL017_LOW_AIR_PRESSURE, severity, timestamp}, ...]

    Trouble->>Svc: getMaintenanceHistory(machineId)
    Svc-->>Trouble: [{ticketType, ticketStatus, createdDate}, ...]

    Trouble->>Man: retrieve(machineId, query="LOW_AIR_PRESSURE", section="troubleshooting")
    Man-->>Trouble: {source: manual, file, page, section, testo causa/rimedio}

    Trouble->>Trouble: sintesi: correla allarmi + manutenzione + procedura manuale
    Trouble-->>Orch: risposta + citazioni (tabella Alarms + pagina manuale)
    Orch-->>U: risposta in streaming con citazioni cliccabili
```

## 3. Richiesta fuori scope (accesso negato)

Esempio: utente con `visibility = technician` chiede dati commerciali. Il divieto è deciso nel Data Access Layer, non nel prompt (contratto trasversale #2).

```mermaid
sequenceDiagram
    actor U as Utente (visibility=technician)
    participant Orch as Orchestrator
    participant Orders as Orders Agent
    participant MCP as commercial-mcp
    participant DAL as Data Access Layer

    U->>Orch: "Quanto è costata la macchina 17478?"
    Orch->>Orch: intent routing → dominio commerciale
    Orch->>Orders: delega (companyId, visibility=technician — mai esposto al modello come parametro)
    Orders->>MCP: crm.getQuoteHistory(machineId=17478)
    MCP->>DAL: query con visibility iniettata lato server
    DAL-->>MCP: ACCESS_DENIED (visibility=technician non ha accesso al dominio commerciale)
    MCP-->>Orders: ACCESS_DENIED (tipizzato)
    Orders-->>Orch: ACCESS_DENIED
    Orch-->>U: "Non hai i permessi per vedere i dati commerciali di questa macchina" (rifiuto esplicito, mai risultato vuoto)
```
