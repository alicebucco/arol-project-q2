# Database operations

This is a maintenance guide for the local database. For the first installation
and to start the application, follow the [main README](../README.md) instead.

Use these commands only when you need to reload data, rebuild an index, or
update an existing database. Run them from the project root with Docker Desktop
running. The commands that use `docker compose exec` also require the
application stack to be up.

`init/002-create-relational-schema.sql` creates the 12 relational tables from
the course workbook. `init/003-create-manual-chunks.sql` adds the local RAG
storage, while `init/005-create-operation-capabilities.sql` adds the planner
capability catalogue.

## Reload the Excel dataset

Use this to import the workbook for the first time, or to discard and reload
all relational data from `data/AROL_Q2_synthetic_fleet_dataset.xlsx`:

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

## Rebuild the manual-search index

Use this after adding, replacing, or re-chunking PDFs under `data/manuals/`.
The manuals remain local and are never committed.

### Create the chunks

Create page-aware chunks locally with:

```bash
docker compose run --rm -v ./data:/workdata backend \
  sh -c "python -m pip install pypdf==6.16.2 && python /db/scripts/chunk_manuals.py /data/manuals --output /workdata/manual_chunks.jsonl"
```

The output is JSONL under the ignored `data/` directory. Each record contains
the source filename, serial number, page, detected section, and text. This
step does not call an API, create embeddings, or write to PostgreSQL.

### Store the embeddings

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
add `--replace` to the Python command.

## Update an existing database schema

Fresh database volumes apply all files in `init/` automatically. If a local
database volume already existed before `003-create-manual-chunks.sql` was
added, apply that migration once before rebuilding the manual index:

```bash
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/003-create-manual-chunks.sql'
```

## Synchronise the planner capability catalogue

Run this whenever an operation is added, removed, or changed in
`backend/core/operations/`. The catalogue stores embeddings of permitted
operation descriptions only: never user questions, manuals, tenant data, or
agent results.

```bash
docker compose exec backend python /db/scripts/index_operation_capabilities.py
```

The script hashes each capability description and recalculates embeddings only
for new or changed operations. Use `--dry-run` to list the capability IDs
without writing to PostgreSQL.
