# ADR 0001 — Backend in Python + FastAPI

## Stato
Accettata

## Contesto
Il frontend è fissato su React + TypeScript. Per il backend serviva scegliere un linguaggio/framework, con un peso particolare dato al layer AI (orchestratore multi-agente, RAG, integrazione MCP), che è la parte più delicata del progetto.

## Decisione
Il Backend API è implementato in **Python con FastAPI**.

Motivazioni:
- L'ecosistema per agenti AI e RAG più maturo oggi è in Python (framework di orchestrazione a grafo, librerie RAG, SDK ufficiale MCP, pandas/openpyxl per l'ingestion del dataset Excel).
- La presentazione AROL stessa suggerisce "Python (FastAPI or ...)" per backend/API, mantenendo coerenza con lo stack indicato dal committente.
- FastAPI supporta nativamente sia REST sia WebSocket, necessari per lo streaming delle risposte verso il frontend.

## Conseguenze
- Il progetto usa due linguaggi (TypeScript nel frontend, Python nel backend) invece di un unico stack full-TypeScript: accettabile perché il focus valutato è l'architettura del layer AI, non l'uniformità linguistica.
- Non è più disponibile la condivisione di tipi/schema tra frontend e backend che si avrebbe con un backend TypeScript: i contratti tra i due container vanno documentati esplicitamente (vedi [`../architecture/02-containers.md`](../architecture/02-containers.md)).
