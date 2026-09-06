# Service Agent ticket contract

`search_tickets(machine_id, user, limit=20, *, ticket_id=None, alarm_id=None,
ticket_status=None, ticket_type=None, priority=None, owner_role=None,
start_date=None, end_date=None)` returns `items`, `machine_id`, `total_count`,
`returned_count`, `is_truncated`, `limit`, `filters`, and `date_field`.

All filters combine with AND. Dates filter `created_date` inclusively. Identifiers
are trimmed and uppercased; blank identifiers are rejected. `alarm_id` is an event
identifier, not an alarm code. Omitted alarm filters retain tickets without alarms.
Labels must match the documented vocabularies exactly. Invalid labels, invalid date
ranges, and non-integer/out-of-range limits raise ValueError before authorisation
and data queries. Limit defaults to 20 and must be between 1 and 100.

Machine authorisation enforces company ownership and operational visibility (`full`
or `technician`) before ticket access. Ordering is `created_date DESC, ticket_id DESC`.
Counts and selected rows come from one SQL snapshot. No pagination beyond the limit
is implemented; callers must not describe a truncated list as exhaustive.

`ticket_detail(machine_id, user, ticket_id)` returns the existing ticket fields only.
A ticket absent from the authorised machine raises `TicketNotFoundError`; no
resolution narrative or completion date is inferred from ticket status.

`maintenance_tickets(machine_id, user, limit=20, **filters)` remains a list-returning
compatibility wrapper. New orchestrator work should call `search_tickets` for
completeness. The old orchestrator is unchanged and still explicitly passes 10.

`GET /machines/{machine_id}/maintenance-tickets` accepts the filters and preserves
its list response body. Headers `X-Total-Count`, `X-Returned-Count`, `X-Is-Truncated`,
and `X-Limit` expose completeness. The frontend is unchanged.
`GET /machines/{machine_id}/maintenance-tickets/{ticket_id}` exposes the detail.
Invalid inputs return 422, missing details return 404, permission failures return 403.

`observed_maintenance_plan`, manual extraction, telemetry aggregation, and their
existing callers are unchanged. Their architectural separation is future work.

Tests: `tests/test_service.py` and the Service test in
`tests/integration/test_postgres_api.py` (requires the disposable integration DB).
