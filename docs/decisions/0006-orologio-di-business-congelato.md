# ADR 0006 — Orologio di business congelato al 2026-08-05

## Stato
Accettata

## Contesto
`istruzioni.md` offre due opzioni per ragionare su scadenze, ritardi e revisioni: trattare il 2026-08-05 come "oggi" (dataset usabile così com'è), oppure ribasare tutti i timestamp alla data reale corrente. La seconda opzione rischia di rompere la coerenza tra date collegate tra loro nel dataset.

## Decisione
Si adotta la prima opzione: **2026-08-05 è "oggi"** per ogni ragionamento su scadenze/ritardi, tramite una singola costante di configurazione (`BUSINESS_TODAY`) usata sia nei prompt di sistema sia nell'aritmetica delle date nelle query SQL.

## Conseguenze
- Nessun `now()`/`datetime.now()` diretto in query o prompt collegati a logica di business: userebbe silenziosamente la data reale di sistema, rompendo ogni risposta su scadenze e ritardi (la data reale al momento di questa decisione è successiva al 2026-08-05).
- Un solo punto di modifica se in futuro si decidesse di ribasare il dataset a una finestra temporale diversa.
- I test/il set di valutazione (vedi [`../architecture/05-data-model.md`](../architecture/05-data-model.md)) devono anch'essi usare `BUSINESS_TODAY`, non la data di esecuzione del test.
