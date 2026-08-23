# ADR 0003 — Tool parametrici fissi invece di NL2SQL libero

## Stato
Accettata

## Contesto
Gli agenti IoT, Orders e Service devono interrogare dati strutturati in Postgres. Un approccio comune è lasciare che il modello generi query SQL libere (NL2SQL). Il dataset però impone un modello di accesso a due livelli (`companyId` tenant + `visibility`, vedi `istruzioni.md`) che non deve mai poter essere aggirato da una query generata dinamicamente.

## Decisione
Ogni agente ha un set **fisso e parametrico** di tool (es. `getRecentAlarms(machineId)`, `getTelemetryTrend(machineId, metric, window)`, `getQuoteHistory(companyId)`), mai una funzione "esegui SQL libero". `companyId` e `visibility` non fanno parte dei parametri visibili al modello: sono iniettati lato server (vedi contratto trasversale #2 in [`../architecture/03-components.md`](../architecture/03-components.md)).

## Conseguenze
- Ogni query possibile è nota e verificabile a priori: determinismo e auditabilità.
- L'enforcement degli accessi vive nel codice dei tool, non nella libertà generativa del modello: un prompt injection non può produrre una query che attraversa il tenant boundary.
- Meno flessibilità nelle domande ad-hoc rispetto a NL2SQL: se un nuovo tipo di domanda ricorre spesso, va aggiunto un nuovo tool esplicito, non delegato al modello.
