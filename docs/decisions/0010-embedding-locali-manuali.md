# ADR 0010 — Embedding locali dei manuali con all-MiniLM-L6-v2

## Stato

Accettata.

## Contesto

Mercury è il provider del modello conversazionale del progetto, ma non espone
un endpoint embedding documentato. I manuali AROL sono materiale riservato e
non devono essere trasmessi a servizi esterni.

## Decisione

Usiamo localmente il modello `sentence-transformers/all-MiniLM-L6-v2` tramite
la libreria Python `sentence-transformers`. Il modello produce vettori densi di
384 dimensioni, normalizzati e salvati in PostgreSQL/pgvector nella tabella
`manual_chunks` con distanza coseno.

Il modello viene scaricato una volta e conservato nel volume Docker locale
`model_cache`; il testo dei manuali non lascia mai il computer.

## Conseguenze

- Mercury resta dedicato a chat, tool calling e sintesi della risposta: non sono
  modificate le sue variabili di configurazione né il suo client.
- `manual_chunks` è una tabella isolata, collegata a `machines` via il seriale
  presente nel nome del manuale; non cambia le tabelle importate dall'Excel.
- La prima esecuzione richiede download del modello e usa CPU e spazio disco
  locali; le esecuzioni successive riusano la cache Docker.
- L'ambiente Docker installa PyTorch nella variante CPU-only: non richiede una
  GPU e non scarica i runtime CUDA non necessari.
- Cambiare modello in futuro richiede rigenerare tutti gli embedding e adeguare
  la dimensione della colonna vettoriale.
