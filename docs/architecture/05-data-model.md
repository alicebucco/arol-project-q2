# Modello dati

Schema verificato contro i nomi reali di fogli e colonne di `data/AROL_Q2_synthetic_fleet_dataset.xlsx` (12 fogli, coerenti con [`../../istruzioni.md`](../../istruzioni.md)), più `manual_chunks`, tabella aggiuntiva per il RAG sui manuali (non fa parte del dataset originale).

## Diagramma entità-relazione

```mermaid
erDiagram
    COMPANIES ||--o{ USERS : ha
    COMPANIES ||--o{ MACHINES : possiede
    COMPANIES ||--o{ QUOTES : riceve
    COMPANIES ||--o{ ORDERS : effettua
    QUOTES ||--o{ ORDERS : "genera (via Orders.quoteId)"
    MACHINE_MODELS ||--o{ MACHINES : istanzia
    MACHINES ||--o{ TELEMETRY_SNAPSHOTS : genera
    MACHINES ||--o{ ALARMS : genera
    MACHINES ||--o{ MAINTENANCE_TICKETS : origina
    ALARMS |o--o{ MAINTENANCE_TICKETS : "può originare (alarmId nullable)"
    MACHINES |o--o{ QUOTE_LINES : "può referenziare (machineId nullable)"
    QUOTES ||--o{ QUOTE_REVISIONS : ha
    QUOTE_REVISIONS ||--o{ QUOTE_LINES : contiene
    ORDERS ||--o{ ORDER_LINES : contiene
    MACHINES ||--o{ MANUAL_CHUNKS : "documentata da (via serialNumber)"

    COMPANIES {
        string companyId PK
        string companyName
        string country
        string sector
        string currency
    }
    USERS {
        string userId PK
        string companyId FK
        string email
        string jobTitle
        enum visibility "full / technician / commercial"
    }
    MACHINE_MODELS {
        string modelId PK
        string modelCode
        int nominalHeads
        string containerType
        string capType
    }
    MACHINES {
        string machineId PK
        string companyId FK
        string modelId FK
        string serialNumber "chiave verso i manuali PDF"
        date deliveryDate
        string configurationProfile "produzione nominale, potenza, tensione: non in MachineModels"
        enum plcFamily
    }
    QUOTES {
        string quoteId PK
        string companyId FK
        date validUntil "usata per il caso: quota approvata dopo scadenza"
    }
    QUOTE_REVISIONS {
        string quoteRevisionId PK
        string quoteId FK
        int revisionNumber "il più alto = corrente"
        enum revisionStatus "Draft / Submitted / Superseded / Approved / Rejected / Expired"
        float discountRate
    }
    QUOTE_LINES {
        string quoteLineId PK
        string quoteRevisionId FK "non esiste quoteId diretto"
        string machineId FK "nullable: riga non legata a una macchina installata"
        float price "già netto di discountRate"
    }
    ORDERS {
        string orderId PK
        string quoteId FK "quota da cui l'ordine è stato generato"
        string companyId FK
        enum orderStatus
        enum shipmentStatus
    }
    ORDER_LINES {
        string orderLineId PK
        string orderId FK
        enum fulfillmentStatus
    }
    TELEMETRY_SNAPSHOTS {
        string telemetryId PK
        string machineId FK
        datetime timestamp "aggregato per ora"
        enum operationalStatus
        float productionRateBph
        float uptimePercentage
        int alarmCount
    }
    ALARMS {
        string alarmId PK
        string machineId FK
        datetime timestamp
        string alarmCode "ALnnn_MNEMONIC"
        enum severity
        enum alarmStatus
    }
    MAINTENANCE_TICKETS {
        string ticketId PK
        string machineId FK
        string alarmId FK "nullable: ticket non originato da un allarme"
        enum ticketType
        enum ticketStatus
        enum priority
        date createdDate
    }
    MANUAL_CHUNKS {
        string chunkId PK
        string machineId FK "via serialNumber, mai misto tra macchine"
        string section "safety / technical_data / mechanical / troubleshooting"
        int page
        vector(384) embedding "all-MiniLM-L6-v2, cosine similarity"
        text content
    }
```

## Semantica che deve vivere nelle query, non nei prompt

Regole esplicite in `istruzioni.md` che un prompt può dimenticare o violare sotto pressione conversazionale — vanno incapsulate nel Data Access Layer ([`03-components.md`](03-components.md)):

- `QuoteLines` si raggiunge da `Quotes` solo passando per `QuoteRevisions` (non esiste `quoteId` diretto sulle righe).
- `QuoteLines.price` è già netto dello sconto di revisione: non riapplicare `discountRate`.
- `OrderLines` non contiene articolo/quantità/prezzo propri: il contenuto di un ordine si ottiene dalle quote lines della revisione approvata.
- La revisione corrente di una quotazione è quella con `revisionNumber` più alto; le altre sono superseded.
- `TelemetrySnapshots.productionRateBph`/`uptimePercentage` sono `0` quando la macchina non produce — non sono indicatori di guasto di per sé.
- La normalità di una lettura di telemetria va giudicata rispetto a `Machines.configurationProfile` (specifico della macchina fisica), non rispetto a `MachineModels` (specifico del modello): due macchine dello stesso modello non sono intercambiabili.

## Inventario edge case noti dal dataset

`istruzioni.md` dichiara esplicitamente che individuare gli edge case è parte della valutazione del progetto. Inventario di partenza (da confermare/estendere quando il dataset reale sarà disponibile):

- FK nulle che un inner join farebbe sparire silenziosamente: `QuoteLines.machineId`, `MaintenanceTickets.alarmId`, `MachineModels.primitiveDiameter`.
- Una company con utenti ma senza macchine.
- Una quotazione approvata dopo la propria scadenza.
- Una quotazione la cui revisione finale è stata rifiutata.
- Macchine le cui ore di servizio accumulate hanno superato una soglia di manutenzione definita nel loro manuale.

Ognuno di questi casi è candidato naturale per il set di valutazione del chatbot (risposta corretta **e** rifiuto/assenza-dato dichiarati esplicitamente, mai un vuoto silenzioso).
