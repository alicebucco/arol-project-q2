# Relational database and Excel import

`init/002-create-relational-schema.sql` creates the 12 tables required by the
Excel dataset. Local RAG storage is added separately by
`init/003-create-manual-chunks.sql`.

When the course workbook is available locally in `data/`, start the database
and run the importer from the temporary Python container:

```bash
docker compose up -d db
docker compose run --rm -e POSTGRES_HOST=db backend \
  sh -c "pip install -r /db/requirements.txt && python /db/scripts/import_excel.py /data/AROL_Q2_synthetic_fleet_dataset.xlsx --replace"
```

`--replace` truncates and reloads every dataset table. Use it for the first
import or to reload the workbook from scratch. Without it, the script stops if
the database already contains data.

Excel headers in camelCase are converted to snake_case. Fields described in
the brief are stored in relational columns; any additional commercial columns
are preserved in `source_data` (JSONB).

## Local PDF chunking (no embeddings yet)

The restricted manuals remain under `data/manuals/` and are never committed.
Create page-aware chunks locally with:

```bash
docker compose run --rm -v ./data:/workdata backend \
  sh -c "python -m pip install pypdf==6.16.2 && python /db/scripts/chunk_manuals.py /data/manuals --output /workdata/manual_chunks.jsonl"
```

The output is JSONL under the ignored `data/` directory. Each record contains
the source filename, serial number, page, detected section, and text. This
step does not call an API, create embeddings, or write to PostgreSQL.

## Local embeddings with pgvector

After importing the Excel dataset and producing `data/manual_chunks.jsonl`,
generate embeddings locally with the English model
`sentence-transformers/all-MiniLM-L6-v2`. The model is downloaded once into a
local Docker volume; manual text is never sent to an external API.

```bash
docker compose run --rm -v ./data:/workdata backend \
  python /db/scripts/embed_manual_chunks.py /workdata/manual_chunks.jsonl
```

The script validates every serial number against `machines.serial_number`, then
stores 384-dimensional normalised vectors in `manual_chunks`. On a rebuild,
add `--replace` to the Python command. Fresh databases create the table through
`init/003-create-manual-chunks.sql`. If the database volume already existed
before this migration was added, apply it once before running the script:

```bash
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/003-create-manual-chunks.sql'
```
