# Manuals Agent contract

`search_with_match_status(machine_id, query, user, limit=5)` authorizes the
machine before local embedding and document access. It returns `manual_evidence`
alongside exact alarm-code status. `search()` remains a list-returning compatibility
wrapper for existing callers.

Each manual evidence item contains the full indexed chunk in `content` and
`excerpt`, its stable `chunk_id`, file, PDF page, and index section. The excerpt is
complete for that indexed chunk, not necessarily for the PDF page or procedure.
Distinct chunks on one page are retained; only identical normalized chunk text on
the same file and page is deduplicated.

`section_category` is an inferred index category. `documented_section_title` is
null because the current index does not preserve a verified PDF heading. `title` is
the neutral label `Manual excerpt`; it is not a manual heading.

When a query contains `ALnnn_MNEMONIC`, `exact_alarm_code_matches` is checked
against the complete authorized manual index. Semantic excerpts remain available
when a code is absent. An exact occurrence proves only that the literal code was
indexed; it does not document a cause or remedy.

Before showing model-generated manual claims, the orchestrator calls
`validate_manual_claim_links(claims, manual_evidence)`. Each claim must contain a
non-empty `claim`, an authorized `chunk_id`, and a `supporting_quote` occurring in
the full source chunk. The validator rebuilds citations from backend evidence and
rejects invented chunk IDs, files, pages, and quotes. It cannot establish logical
entailment from natural language; the structured-composition prompt therefore
requires cautious wording and the orchestrator discards rejected claims.

`maintenance_requirements(machine_id, user)` returns explicit working-hour and
operating-hour intervals with the source chunk, citation, and source-derived
condition sentences. It does not read telemetry or tickets and never determines
that maintenance is due. The orchestrator combines this documentary evidence
with `iot.observed_productive_hours()`.
