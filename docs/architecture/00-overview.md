# Architecture Overview

This is the entry point for the architecture documentation of the **AROL
Customer Platform**: a conversational application for industrial fleet
management, manual retrieval, and assisted troubleshooting.

The documentation follows the **C4 model** (Context → Containers → Components)
and complements it with dynamic-flow and data-model diagrams.

| Document | C4 level | Content |
| --- | --- | --- |
| [`01-context.md`](01-context.md) | 1 — System Context | Users, system boundary, and external services. |
| [`02-containers.md`](02-containers.md) | 2 — Containers | Deployable services and their communication paths. |
| [`03-components.md`](03-components.md) | 3 — Components | Backend modules, routing, agents, and access control. |
| [`04-dynamic-flows.md`](04-dynamic-flows.md) | Supplementary | Login, manual retrieval, and role-denied request flows. |
| [`05-data-model.md`](05-data-model.md) | Supplementary | Entity relationships and dataset semantics. |

The design choices behind this implementation are recorded in
[`docs/decisions.md`](../decisions.md).

## Implementation principles

- **Machine-specific context.** A manual belongs to a physical machine through
  its serial number, not merely to a model.
- **Local manual RAG.** PDF text is chunked and embedded locally; it is not
  passed to the external LLM. Search results contain an excerpt and a
  file/page citation, rather than raw chunk text.
- **Server-side access control.** Company and visibility boundaries are applied
  in the API and SQL queries. They are not delegated to the model.
- **Structured evidence.** The chat UI renders manual citations and structured
  records for operational and commercial answers.
- **Simple deployment.** Docker Compose runs the frontend, backend, database,
  and development-only Adminer service locally.

## Scope

The repository contains the application source, Docker infrastructure,
architecture documents, and local ingestion tooling. The supplied Excel
workbook and PDF manuals remain in the Git-ignored `data/` directory and are
not part of the repository.
