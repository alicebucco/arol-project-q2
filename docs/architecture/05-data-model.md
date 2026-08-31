# Data Model

The schema is based on the supplied Excel workbook and is extended with
`manual_chunks`, the local RAG table. The workbook and manuals remain in the
Git-ignored `data/` directory.

## Entity-relationship diagram

```mermaid
erDiagram
    COMPANIES ||--o{ USERS : has
    COMPANIES ||--o{ MACHINES : owns
    COMPANIES ||--o{ QUOTES : receives
    COMPANIES ||--o{ ORDERS : places
    QUOTES ||--o{ ORDERS : "generates"
    MACHINE_MODELS ||--o{ MACHINES : defines
    MACHINES ||--o{ TELEMETRY_SNAPSHOTS : produces
    MACHINES ||--o{ ALARMS : raises
    MACHINES ||--o{ MAINTENANCE_TICKETS : has
    ALARMS |o--o{ MAINTENANCE_TICKETS : "may create"
    MACHINES |o--o{ QUOTE_LINES : "may reference"
    QUOTES ||--o{ QUOTE_REVISIONS : has
    QUOTE_REVISIONS ||--o{ QUOTE_LINES : contains
    ORDERS ||--o{ ORDER_LINES : contains
    MACHINES ||--o{ MANUAL_CHUNKS : "is documented by"

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
        string serialNumber "key to the PDF manual"
        date deliveryDate
        string configurationProfile "machine-specific production, power, voltage"
        string plcFamily
    }
    QUOTES {
        string quoteId PK
        string companyId FK
        date validUntil
    }
    QUOTE_REVISIONS {
        string quoteRevisionId PK
        string quoteId FK
        int revisionNumber "highest value is current"
        string revisionStatus
        float discountRate
    }
    QUOTE_LINES {
        string quoteLineId PK
        string quoteRevisionId FK "no direct quoteId"
        string machineId FK "nullable"
        float price "already net of discount"
    }
    ORDERS {
        string orderId PK
        string quoteId FK
        string companyId FK
        string orderStatus
        string shipmentStatus
    }
    ORDER_LINES {
        string orderLineId PK
        string orderId FK
        string fulfillmentStatus
    }
    TELEMETRY_SNAPSHOTS {
        string telemetryId PK
        string machineId FK
        datetime timestamp
        string operationalStatus
        float productionRateBph
        float uptimePercentage
        int alarmCount
    }
    ALARMS {
        string alarmId PK
        string machineId FK
        datetime timestamp
        string alarmCode
        string severity
        string alarmStatus
    }
    MAINTENANCE_TICKETS {
        string ticketId PK
        string machineId FK
        string alarmId FK "nullable"
        string ticketType
        string ticketStatus
        string priority
        date createdDate
    }
    MANUAL_CHUNKS {
        string chunkId PK
        string machineId FK
        string section
        int page
        vector(384) embedding "local MiniLM cosine similarity"
        text content "kept internal to the backend"
    }
```

## Query semantics

The following rules belong in the data-access layer, not in LLM prompts:

- A quote line is reached from a quote through `QuoteRevisions`; it has no direct `quoteId`.
- `QuoteLines.price` is already net of the revision discount and must not be discounted again.
- An order's content is obtained from the lines of its approved quote revision.
- The current quote revision is the one with the highest `revisionNumber`.
- Quote expiry is evaluated against the fixed business date `2026-08-05`;
  a quote is expired only when `validUntil` is earlier than that date.
- A zero production rate or uptime value can mean that a machine is not producing; it is not automatically a fault.
- Telemetry production is interpreted against the physical machine's `configurationProfile`, not only against the shared machine model. When the machine is `Running`, the API compares the rate with the nominal `bph` extracted from that profile using a ±10% reference band. A zero rate outside `Running` is reported as not assessed, not as a fault.

## Important edge cases

- Nullable foreign keys: `QuoteLines.machineId`, `MaintenanceTickets.alarmId`, and `MachineModels.primitiveDiameter`.
- A company can have users without any machines.
- A quote can be approved after its validity date, or end with a rejected revision.
- Machines of the same model may have different configuration profiles.
- Maintenance thresholds can be documented only in the machine-specific manual.
