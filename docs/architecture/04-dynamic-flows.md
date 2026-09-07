# Dynamic Flows

These sequence diagrams describe three representative flows: authentication,
context-aware local manual retrieval with grounded composition, and a request
rejected by role policy.

## 1. Login

```mermaid
sequenceDiagram
    actor U as Customer user
    participant FE as Frontend
    participant API as Backend API
    participant DB as PostgreSQL

    U->>FE: Enters user ID and password
    FE->>API: POST /auth/login
    API->>DB: Read user and bcrypt password hash
    DB-->>API: User, company, visibility, hash
    API->>API: Verify password and sign JWT
    API-->>FE: JWT and user profile
    FE-->>U: Opens authenticated application
```
## 2. Manual question

```mermaid
sequenceDiagram
    actor U as Customer user
    participant FE as Frontend
    participant API as Backend API
    participant LLM as External LLM
    participant M as Manuals agent
    participant DB as PostgreSQL + pgvector

    U->>FE: “What are the installation requirements?”
    FE->>API: POST /chat with JWT, machine context, and bounded prior display turns
    API->>API: Resolve company and visibility
    API->>LLM: Request one contextual structured plan, when history exists
    Note over API: Conversation text is context only, never authorised evidence
    LLM-->>API: manuals.search with typed parameters
    API->>API: Validate operation, machine context, and parameters
    API->>M: Retrieve for the authorised machine
    M->>DB: Vector search and local re-ranking
    DB-->>M: Relevant local chunks and metadata
    M-->>API: Excerpts and file/page citations
    API->>LLM: Bounded authorised excerpts and citations
    LLM-->>API: Grounded English answer
    API-->>FE: English answer, manual sources, and structured data
    FE-->>U: Answer with expandable source cards
    Note over API: PDFs, PostgreSQL, vector index, and raw chunks never leave the backend
```

## 3. Request outside the user's role

```mermaid
sequenceDiagram
    actor U as Technician
    participant FE as Frontend
    participant API as Backend API
    participant O as Orders agent
    participant DB as PostgreSQL

    U->>FE: “What did this machine cost?”
    FE->>API: POST /chat with JWT
    API->>O: Commercial-data request
    O->>O: Check visibility = commercial
    O-->>API: HTTP 403 Access denied
    API-->>FE: Explicit access denial
    FE-->>U: “You do not have access to commercial data.”
```

## Temporary conversational context

While the chat drawer remains open, the frontend sends at most the eight most
recent completed display turns with the next message. When the planner is
enabled, the backend gives those text-only turns to a contextual planner only
when the new message depends on an earlier subject or time, such as "that
alarm" or "yesterday". A self-contained question, including one with an
explicit code or a new subject, is planned independently of earlier turns. A
contextual plan must either ask for clarification or declare and preserve every
identifier that it actually inherits in its parameters. The backend rejects a
plan that introduces, drops, or loosens an inherited reference, then retrieves
fresh authorised evidence through the operation registry. The context is never
persisted or treated as evidence. Manual excerpts, sources, structured data,
and private manual chunks are excluded from the conversational context payload.
