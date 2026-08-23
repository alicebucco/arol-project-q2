# Ciao Alice — guida per iniziare

Questo documento è diverso dagli altri nella cartella `docs/`: quelli sono documentazione tecnica di architettura, pensata per chi già conosce sviluppo software. Questo è per te, per partire da zero: non deve darti per scontato **niente** su frontend, backend, database, Docker o intelligenza artificiale. Se una parola tecnica non ti è chiara, cercala qui prima di cercarla altrove — è probabile che sia spiegata.

Non c'è ancora codice scritto in questo repository: solo documentazione (cosa costruire e perché) e un file che fa partire l'infrastruttura (Docker Compose). Il codice vero lo scriverai tu — questo documento ti spiega come muoverti.

---

## 1. Le tecnologie, spiegate da zero

Il progetto è un chatbot che risponde a domande su macchinari industriali (allarmi, manutenzione, preventivi...) usando l'intelligenza artificiale. Per farlo servono diversi "pezzi" software che lavorano insieme. Pensa a un ristorante:

- la **sala** è quello che il cliente vede e tocca (il menu, i tavoli) → questo è il **frontend**
- la **cucina** prepara i piatti seguendo le richieste, ma il cliente non la vede → questo è il **backend**
- la **dispensa** è dove sono conservati gli ingredienti → questo è il **database**

### Frontend — React + TypeScript

Il frontend è tutto quello che l'utente vede e con cui interagisce nel browser: la finestra della chat, i pulsanti, il testo che appare mentre il chatbot "scrive".

- **React** è una libreria molto diffusa per costruire interfacce web componendo piccoli pezzi riutilizzabili ("componenti") — es. un componente "bolla di messaggio", uno "campo di testo", uno "pulsante invia".
- **TypeScript** è JavaScript (il linguaggio con cui gira quasi tutto il web) con l'aggiunta dei **tipi**: dichiari esplicitamente che una variabile è un numero, un testo, ecc. Il vantaggio è che molti errori banali (es. passare un testo dove ci si aspettava un numero) vengono segnalati mentre scrivi il codice, non quando l'app è già in mano all'utente.

### Backend — Python + FastAPI

Il backend è il programma che gira su un server (non nel browser dell'utente) e fa il lavoro "pesante": riceve la domanda dell'utente, decide come rispondere, parla con il database e con l'intelligenza artificiale, e rimanda indietro la risposta.

- **Python** è il linguaggio di programmazione scelto per questa parte.
- **FastAPI** è un framework (un insieme di strumenti già pronti) per scrivere velocemente un backend che risponde a richieste web, in Python.

### Database — PostgreSQL + pgvector

Il database è dove i dati vivono in modo permanente: le aziende clienti, le macchine, gli allarmi, i preventivi. Senza database, ogni volta che spegni il computer perderesti tutto.

- **PostgreSQL** (spesso abbreviato "Postgres") è un database **relazionale**: i dati sono organizzati in tabelle con righe e colonne, un po' come fogli Excel collegati tra loro (es. la tabella "Macchine" è collegata alla tabella "Aziende" tramite un identificativo comune).
- **pgvector** è un'estensione di Postgres che permette di salvare e cercare anche un tipo di dato particolare: i **vettori di embedding** (vedi più sotto, sezione RAG). In pratica: lo stesso database che tiene le tabelle "normali" tiene anche i dati per la ricerca intelligente nei manuali, invece di usare due sistemi separati.

### Docker e Docker Compose

Installare Python, Postgres, Node.js e farli parlare tra loro sul tuo computer può essere lungo e pieno di intoppi diversi da persona a persona ("sul mio computer funziona..."). **Docker** risolve questo: impacchetta ogni pezzo del sistema (frontend, backend, database) in un "contenitore" isolato, già pronto, uguale su qualunque computer.

**Docker Compose** è lo strumento che accende *tutti* i contenitori insieme con un solo comando, invece di doverli avviare uno per uno. In questo repository, il file [`docker-compose.yml`](docker-compose.yml) descrive i 3 contenitori del progetto (frontend, backend, database) e come devono parlarsi.

### Cos'è un LLM (e perché conta)

**LLM** sta per *Large Language Model* ("modello di linguaggio di grandi dimensioni"): un sistema di intelligenza artificiale addestrato su enormi quantità di testo, capace di leggere una domanda in linguaggio naturale e generare una risposta altrettanto naturale. È il "motore" che dà al chatbot la capacità di capire le domande e formulare risposte comprensibili — di per sé, però, **non conosce i dati di questo progetto** (non sa niente delle macchine AROL): quei dati gliel'li dobbiamo fornire noi, con le tecniche descritte sotto.

Un LLM si usa tramite un'**API**: mandi una richiesta via internet a un servizio esterno (in questo progetto si chiama **Mercury**, di Inception Labs) con una chiave segreta che ti identifica (`LLM_API_KEY` nel file `.env`, che **non va mai condiviso pubblicamente o messo su GitHub**), e ricevi indietro una risposta generata.

### Agenti, Orchestratore, RAG, MCP — l'intelligenza artificiale "su misura"

Questa è la parte concettualmente più nuova, ma l'idea di fondo è semplice. Immagina un centralino telefonico di un'azienda con più reparti specializzati:

- Chiami il centralino (**l'Orchestratore**) e spieghi cosa ti serve.
- Il centralino capisce di che tipo di richiesta si tratta e ti gira al reparto giusto — o a più reparti insieme se la domanda è complessa.
- Ogni reparto (**un Agente**) è specializzato in una cosa sola e sa fare bene solo quella: un reparto sa tutto sui manuali tecnici, un altro sa leggere i dati dei sensori delle macchine, un altro conosce preventivi e ordini.

Nel nostro progetto ci sono 5 "reparti" (**5 Agenti**, dettagliati in [`docs/architecture/03-components.md`](docs/architecture/03-components.md)): uno per i manuali, uno per i sensori (IoT), uno per preventivi/ordini, uno per la manutenzione, e uno che fa da "diagnostico" mettendo insieme le informazioni degli altri quando la domanda è complessa (es. *"perché questa macchina continua a dare problemi?"*).

Due concetti tecnici che userai spesso:

- **RAG** (*Retrieval-Augmented Generation*) — è la tecnica con cui l'agente dei manuali risponde usando davvero il contenuto dei manuali PDF, invece di "inventare" (gli LLM, se lasciati liberi, a volte inventano risposte plausibili ma sbagliate — si chiama *allucinazione*). Funziona così: il testo dei manuali viene spezzettato in piccoli pezzi ("chunk"), ogni pezzo viene trasformato in una lista di numeri che ne rappresenta il significato (**embedding**, salvato in pgvector), e quando arriva una domanda si cercano i pezzi di manuale più simili al significato della domanda, che vengono dati all'LLM come "materiale di consultazione" prima che scriva la risposta. In pratica: prima cerca, poi genera — non genera e basta.
- **MCP** (*Model Context Protocol*) — è un modo standard con cui un agente AI chiama delle funzioni per andare a prendere dati reali (es. "dammi gli ultimi allarmi della macchina X"), invece di inventarsi i numeri. Pensa a MCP come al modulo con cui il reparto del centralino telefona davvero al magazzino per sapere cosa c'è in stock, invece di tirare a indovinare.

---

## 2. Come è organizzato questo repository

```
progetto-alice/
├── README.md            ← punto d'ingresso "tecnico", con il quickstart Docker
├── ALICE.md              ← questo file
├── TECHSTACK.md          ← tabella riassuntiva delle tecnologie scelte
├── docker-compose.yml    ← fa partire i 3 servizi con un comando
├── .env.example          ← modello delle variabili segrete/di configurazione da compilare
├── db/init/              ← script minimo eseguito alla prima creazione del database
├── data/                 ← il dataset del corso (Excel + manuali PDF) — leggi la sezione 5 qui sotto
├── docs/
│   ├── architecture/      ← documentazione tecnica dell'architettura (livelli C4)
│   └── decisions/         ← perché abbiamo scelto ogni tecnologia/approccio
├── istruzioni.md          ← il brief originale del corso: dati disponibili, regole, domande di esempio
└── AROL-presentation-project-Q2.pdf   ← la presentazione originale di AROL
```

`backend/` e `frontend/` **non esistono ancora**: li creerai tu, seguendo la struttura descritta in `docs/architecture/`.

---

## 3. Recap veloce dei documenti — cosa leggere, in che ordine

Non serve leggere tutto subito. Ordine consigliato:

1. **[`istruzioni.md`](istruzioni.md)** — il punto di partenza vero: cosa contiene il dataset, le regole di accesso ai dati, gli esempi di domande. Leggilo per intero almeno una volta, con calma.
2. **[`docs/architecture/00-overview.md`](docs/architecture/00-overview.md)** — l'indice della documentazione tecnica, con una tabella che confronta ogni pezzo dell'architettura con le slide originali di AROL (utile se qualcuno ti chiede "perché avete fatto così invece che cosà").
3. **[`docs/architecture/01-context.md`](docs/architecture/01-context.md)** — la vista più semplice: chi usa il sistema, con quale servizio esterno parla (Mercury).
4. **[`docs/architecture/02-containers.md`](docs/architecture/02-containers.md)** — i 3 pezzi (frontend, backend, database) e come comunicano.
5. **[`docs/architecture/03-components.md`](docs/architecture/03-components.md)** — il documento più corposo: come è fatto internamente il backend, i 5 agenti, le regole di sicurezza sui dati. Qui c'è il cuore della parte AI.
6. **[`docs/architecture/04-dynamic-flows.md`](docs/architecture/04-dynamic-flows.md)** — 3 esempi concreti passo-passo (scansione QR, domanda complessa, domanda a cui il sistema deve rifiutarsi di rispondere).
7. **[`docs/architecture/05-data-model.md`](docs/architecture/05-data-model.md)** — come sono fatte le tabelle dei dati, con le "trappole" del dataset già individuate (dati mancanti, regole di calcolo particolari).
8. **[`docs/decisions/`](docs/decisions/README.md)** — 8 schede brevi, una per ogni scelta tecnica importante, col perché. Consultale quando ti chiedi "perché è stato scelto così?" prima di cambiare qualcosa — spesso il perché non è ovvio.
9. **[`TECHSTACK.md`](TECHSTACK.md)** — tabella riassuntiva veloce delle tecnologie, da tenere sottomano.

---

## 4. Come lavorare sul codice

### Procedi a piccoli passi, non tutto insieme

Non provare a costruire tutto il sistema in una volta: è il modo più veloce per bloccarsi. Un ordine ragionevole:

1. **Prepara i dati**: scrivi uno script che legge il file Excel in `data/` e lo carica nelle tabelle di Postgres (vedi lo schema in [`05-data-model.md`](docs/architecture/05-data-model.md)); poi uno script che spezzetta i manuali PDF e crea gli embedding.
2. **Un backend minimo che funziona davvero**: prima di scrivere i 5 agenti, fai un solo endpoint che riceve una domanda, la manda a Mercury, e restituisce la risposta — senza dati, senza agenti. Serve a verificare che tutti i pezzi (Docker, backend, chiave API) si parlino, prima di costruirci sopra la complessità.
3. **Un agente alla volta**: parti da quello più semplice (es. Manuals Agent) e fallo funzionare bene prima di passare al successivo.
4. **L'Orchestratore**, che decide quale agente usare, solo dopo che almeno 2-3 agenti esistono e funzionano da soli.
5. **Il frontend**, collegato per ultimo: è più facile costruire l'interfaccia quando sai già che cosa il backend restituisce davvero.
6. **I controlli di accesso** (chi può vedere cosa) vanno testati con casi concreti fin da subito, non aggiunti "alla fine": sono descritti in [`03-components.md`](docs/architecture/03-components.md) e sono una parte valutata del progetto.

Se ti blocchi su un pezzo, è del tutto normale saltarlo temporaneamente con un "finto" risultato (es. l'agente risponde con un testo fisso) e tornarci dopo — meglio avere tutto il sistema che gira in modo semplificato che un solo pezzo perfetto e il resto fermo.

### Docker Compose — i comandi che userai

```bash
docker compose up          # accende tutto (frontend, backend, database)
docker compose up -d       # come sopra, ma in background (ti restituisce il terminale)
docker compose logs -f backend   # mostra cosa sta stampando il backend, utile per capire errori
docker compose down        # spegne tutto
```

C'è anche un quarto servizio, **Adminer** (`http://localhost:8080` a container avviati): un'interfaccia da browser per guardare dentro al database — tabelle, righe, colonne — senza scrivere query SQL a mano. Utile soprattutto nella Fase 1 (sezione precedente), per controllare che i dati dell'Excel siano stati caricati correttamente. Per accedere: sistema `PostgreSQL`, server `db`, utente/password/database quelli che hai messo in `.env`.

Se qualcosa non parte, il primo posto dove guardare è sempre `docker compose logs -f <nome-servizio>` (`db`, `backend` o `frontend`): quasi sempre l'errore vero è scritto lì, in mezzo a molte righe — cerca la parola `Error` o `Traceback`.

### Git — come non perdere il lavoro

Git è lo strumento che tiene la "storia" delle modifiche al codice (già in uso in questo repository: ogni "commit" è un punto di salvataggio). Poche regole pratiche:

- **Fai commit spesso e piccoli**, non un unico commit enorme a fine giornata: se qualcosa si rompe, è molto più facile capire quale commit ha introdotto il problema.
- Scrivi messaggi di commit brevi ma chiari su *cosa* hai fatto (es. `"aggiungo endpoint per interrogare gli allarmi"`, non `"fix"`).
- Prima di modificare/cancellare qualcosa che non hai scritto tu, fai `git status` per vedere cosa cambieresti, e chiedi se non sei sicura.
- Va benissimo lavorare direttamente sul branch principale (`main`) per un progetto di questa dimensione: non serve una strategia di branch complicata, a meno che il tuo gruppo non preferisca separare il lavoro in corso da quello già "stabile".

---

## 5. Attenzione: i manuali AROL hanno una licenza restrittiva

Nella cartella `data/manuals/`, ogni PDF ha a pagina 2 una nota che dice esplicitamente: **non pubblicare né caricare questo documento su nessun repository di codice, pubblico o privato**, e cancellarne tutte le copie a fine corso.

Questi file erano stati committati e pushati per errore su GitHub: il problema è stato risolto rimuovendo quel commit dalla cronologia con un force-push (verificato: non è più raggiungibile dal remote), e `data/` è ora in [`.gitignore`](.gitignore) così non può ricapitare per sbaglio. Il dataset resta comunque sul tuo computer in `data/` — serve per lavorare, semplicemente non deve mai finire in un commit. Se in futuro hai dubbi su come trattare questo materiale, i contatti del corso/AROL sono in fondo a [`istruzioni.md`](istruzioni.md).

---

## 6. Mini-glossario di riferimento rapido

| Termine | Cosa significa qui |
|---|---|
| **Frontend** | La parte dell'app che l'utente vede nel browser |
| **Backend** | Il programma sul server che fa il lavoro "dietro le quinte" |
| **API** | Il modo in cui due programmi si scambiano richieste/risposte (es. frontend↔backend, backend↔Mercury) |
| **Database** | Dove i dati sono salvati in modo permanente |
| **Container / Docker** | Un "pacchetto" isolato che contiene un pezzo del sistema già pronto per funzionare |
| **LLM** | Il modello di intelligenza artificiale che genera testo (qui: Mercury) |
| **Agente** | Un "reparto specializzato" di intelligenza artificiale, focalizzato su un tipo di dato/domanda |
| **Orchestratore** | Il "centralino" che decide quale agente coinvolgere per ogni domanda |
| **RAG** | Tecnica per far rispondere l'LLM basandosi sul vero contenuto dei manuali, non a memoria |
| **Embedding** | La "traduzione in numeri" di un testo, usata per cercare i pezzi di manuale più pertinenti |
| **MCP** | Il protocollo standard con cui un agente chiama funzioni per leggere dati veri (non inventati) |
| **companyId** | L'identificativo dell'azienda cliente: un utente non deve mai vedere dati di un'altra azienda |
| **visibility** | Il "ruolo" di un utente (`full`/`technician`/`commercial`): determina quali dati può chiedere |

---

Se qualcosa in questo documento non basta a capire un pezzo dell'architettura, il passo successivo è leggere il documento tecnico corrispondente in `docs/architecture/` — è scritto per andare più a fondo su esattamente questi concetti.
