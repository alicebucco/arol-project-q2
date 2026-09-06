# Orders Agent contract

All operations require an authenticated `AuthContext`. Commercial visibility is
restricted to `full` and `commercial`; company scope always comes from that context.
No operation creates or changes commercial records.

## Search operations

- `search_orders(user, limit=20, *, machine_id=None, order_id=None, quote_id=None,
  order_status=None, shipment_status=None, start_date=None, end_date=None)`
- `search_quotes(user, limit=20, *, machine_id=None, quote_id=None,
  revision_status=None, start_date=None, end_date=None)`

Results contain `items`, `total_count`, `returned_count`, `is_truncated`, `limit`,
`filters`, `company_id`, and `date_field`. Totals and page rows use one SQL statement
and the same database snapshot. Ordering remains descending document ID, not date.
`limit` must be an integer from 1 to 100; booleans are rejected. The default is 20.
A truncated list must not be described as exhaustive. A caller can request up to 100
rows; pagination beyond that is not implemented.

Status labels must exactly match the controlled vocabularies in `instructions.md`.
Invalid labels and reversed periods raise `ValueError` before data access.
Identifiers are trimmed and uppercased; blank identifiers are rejected. Well-formed
but unknown search identifiers return an empty result within the user's company.
Dates must be Python `date` values. Boundaries are inclusive: order date for orders,
quote creation date for quotes. Missing dates do not match a supplied date filter.

Machine filters select documents through the highest approved revision for orders
and the latest revision for quotes. They never restrict the lines used for quote
totals. Quote totals sum already-net prices without applying discounts again.
Currency accompanies amounts. Latest quote revision does not mean approved revision.

## Details and revision evidence

- `order_detail(user, order_id)` reuses the existing approved-revision lookup.
- `quote_history(user, quote_id)` returns all revisions and lines, source
  `change_summary` values, and a calculated comparison of the last two revisions.

Line comparison uses machine ID and normalised description, not a stable identity
across revisions. Description changes appear as removal/addition. Duplicate keys
produce `ambiguous` entries retaining both groups of original lines. No price change
is inferred for ambiguous groups. `comparison_basis` explains this limitation.
Source change summaries remain separate from calculated differences.

The order lookup selects the highest approved revision. In the inspected local
workbook every order has exactly one approved revision; multiple-approved-revision
policy has not been redesigned. Missing/foreign details raise the existing not-found
exceptions; HTTP endpoints map these to 404.

## Existing callers and HTTP compatibility

`orders()` and `quotes()` remain list-returning compatibility wrappers, with default
20 and the same optional filters. New orchestrator work should use `search_orders()`
and `search_quotes()` to receive completeness metadata. The current orchestrator is
unchanged and still explicitly requests 10 through the compatibility wrappers.

`GET /orders` and `GET /quotes` preserve list response bodies and accept the search
filters. Completeness is exposed through `X-Total-Count`, `X-Returned-Count`,
`X-Is-Truncated`, and `X-Limit` response headers, also exposed through CORS.
The frontend has not been changed to display those headers. Detail endpoints now
call the agent. Invalid filters map to HTTP 422.

## Verification

Agent/API unit tests cover validation, permission rejection, argument forwarding,
metadata, and ambiguous comparisons. PostgreSQL coverage is in
`tests/integration/test_postgres_api.py` and requires the existing disposable
integration database. No test adds cases to the local evaluation dataset.
