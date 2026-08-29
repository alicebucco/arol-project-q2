# Dynamic Flows

These sequence diagrams describe three representative flows: authentication,
local manual retrieval, and a request rejected by role policy.

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
    participant M as Manuals agent
    participant DB as PostgreSQL + pgvector

    U->>FE: “What are the installation requirements?”
    FE->>API: POST /chat with JWT and machine context
    API->>API: Resolve company and visibility
    API->>M: Retrieve for the authorised machine
    M->>DB: Vector search and local re-ranking
    DB-->>M: Relevant local chunks and metadata
    M-->>API: Excerpts and file/page citations
    API-->>FE: English answer and manual sources
    FE-->>U: Answer with expandable source cards
    Note over API: No manual chunk is sent to the external LLM
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
