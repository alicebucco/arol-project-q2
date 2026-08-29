# C4 — Level 1: System Context

## Purpose

The **AROL Customer Platform** helps customer-company users ask questions about
their fleet, technical manuals, alarms, maintenance records, quotes, and
orders. It keeps the supplied synthetic dataset and restricted manuals within
the local environment.

## Actors and external systems

- **Customer user** — an operator, technician, or commercial contact. Their
  company and visibility profile determine what information they can access.
- **LLM provider** — an external OpenAI-compatible chat-completion API used for
  general and structured-data answers. The backend is the only component that
  calls it.

The Excel workbook and the manuals are local project data, not external
systems. Manual text is embedded and retrieved locally, and never passed to the
LLM provider.

## Diagram

```mermaid
flowchart TB
    classDef person fill:#08427b,stroke:#052e56,color:#ffffff
    classDef system fill:#1168bd,stroke:#0b4884,color:#ffffff
    classDef external fill:#999999,stroke:#6b6b6b,color:#ffffff

    User["<b>Customer user</b><br/>Operator, technician, or<br/>commercial contact"]:::person

    subgraph Boundary["AROL Customer Platform"]
        System["<b>AROL Customer Platform</b><br/>Authenticated chat for fleet management,<br/>manual retrieval, and troubleshooting"]:::system
    end

    LLM["<b>LLM provider</b><br/>External chat-completion API"]:::external

    User -->|"Uses the web application (HTTPS)"| System
    System -->|"English answers, records, and citations"| User
    System -->|"General or structured-data prompts only (HTTPS)"| LLM
    LLM -->|"Chat completion"| System
```
