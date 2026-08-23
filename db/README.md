# Relational database and Excel import

`init/002-create-relational-schema.sql` creates only the 12 tables required by
the Excel dataset. PDF and RAG processing are intentionally out of scope.

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
