# AROL Customer Platform

Progetto universitario: un'app conversazionale ad agenti AI per la gestione della flotta industriale e il troubleshooting autonomo, sviluppato a partire dal brief AROL × Politecnico di Torino.

> **Non hai esperienza con backend/frontend/database/Docker/AI?** Parti da [`ALICE.md`](ALICE.md) invece che da questo file: spiega tutto da zero.

- Specifica del dataset e del modello di accesso: [`istruzioni.md`](istruzioni.md)
- Presentazione del committente: [`AROL-presentation-project-Q2.pdf`](AROL-presentation-project-Q2.pdf)
- **Documentazione architetturale (modello C4 + Mermaid):** [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md)
- **Decisioni di design motivate (ADR):** [`docs/decisions/`](docs/decisions/README.md)
- **Stack tecnologico:** [`TECHSTACK.md`](TECHSTACK.md)

## Cosa contiene questo repository

Solo documentazione architetturale e infrastruttura Docker — **non l'applicazione**. `backend/` e `frontend/` non esistono ancora: la loro struttura interna attesa è descritta in [`docs/architecture/02-containers.md`](docs/architecture/02-containers.md) e [`docs/architecture/03-components.md`](docs/architecture/03-components.md).

## Avvio rapido

```bash
cp .env.example .env   # compilare LLM_API_KEY e le credenziali del DB
docker compose up
```

Porta su 4 servizi: i 3 dell'architettura logica (frontend, backend, database) più **Adminer** (`http://localhost:8080`), un tool da browser per ispezionare il database senza scrivere query a mano — vedi [`docker-compose.yml`](docker-compose.yml) e [`TECHSTACK.md`](TECHSTACK.md). Il comando funziona solo dopo aver popolato `backend/` e `frontend/` secondo la documentazione di architettura.

## Dataset

Il dataset sintetico è in [`data/`](data/) (`AROL_Q2_synthetic_fleet_dataset.xlsx` + `data/manuals/`), coerente con lo schema descritto in [`docs/architecture/05-data-model.md`](docs/architecture/05-data-model.md).

> **Attenzione — materiale AROL a uso didattico ristretto.** Ogni manuale in `data/manuals/` contiene a pagina 2 una notice che vieta esplicitamente la pubblicazione/upload "to any website, public or private code repository" e ne impone la cancellazione a fine corso (vedi anche il disclaimer in [`istruzioni.md`](istruzioni.md)). Il commit che li aveva aggiunti è stato rimosso dalla cronologia locale e da GitHub con un force-push (verificato: `origin/main` non lo contiene più) e `data/` è ora in [`.gitignore`](.gitignore), quindi non verrà ricommittato per errore. Dettagli in [`ALICE.md`](ALICE.md#5-attenzione-i-manuali-arol-hanno-una-licenza-restrittiva).
