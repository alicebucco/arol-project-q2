# ADR 0009 — Ingestion locale dei manuali PDF con pypdf

## Stato

Accettata.

## Contesto

I manuali AROL sono materiale didattico riservato: non possono essere pubblicati
né distribuiti tramite Git. Il progetto deve però estrarne testo, pagina e
provenienza per il futuro Manuals Agent basato su RAG.

Un test sul manuale `15610_manual_EN.pdf` ha confermato che tutte le sue pagine
contengono testo estraibile; non è quindi necessario introdurre OCR nella prima
versione della pipeline.

## Decisione

- I PDF restano esclusivamente in `data/manuals/`, cartella già ignorata da Git.
- La pipeline usa `pypdf` per leggere il testo e conserva sempre numero di pagina
  e nome del file come metadati di provenienza.
- Il seriale della macchina viene ricavato dal nome del file (`<serial>_manual_EN.pdf`)
  e in seguito validato contro `machines.serial_number`.
- Il testo estratto viene normalizzato prima di essere diviso in chunk. OCR sarà
  aggiunto solo se un manuale futuro non contiene una text layer utilizzabile.

## Conseguenze

- I manuali non entrano mai in commit, push o immagini Docker: Docker li monta
  localmente in sola lettura.
- Le risposte del Manuals Agent potranno citare file e pagina, rendendo le fonti
  verificabili durante una diagnosi.
- La pipeline non dipende da un servizio OCR e resta semplice da eseguire in
  locale.
- La scelta del modello/provider di embedding resta separata: Mercury è il
  provider del modello conversazionale, non quello degli embedding.
