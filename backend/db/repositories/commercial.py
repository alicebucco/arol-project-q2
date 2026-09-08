"""PostgreSQL repository for commercial data."""

from typing import Any

from core.business_time import quote_validity_status
from core.db import connection
from db.repositories.errors import OrderNotFoundError, QuoteNotFoundError


async def get_company_orders(company_id: str, limit: int) -> list[dict[str, Any]]:
    """Compatibility list for an already-authorised company."""
    return (await search_company_commercial(company_id, "orders", limit))["items"]

async def get_company_order_detail(company_id: str, order_id: str) -> dict[str, Any]:
    """Return an order's fulfilment and the content of its approved quote revision."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT o.order_id, o.quote_id, o.order_status, o.shipment_status,
                       q.source_data ->> 'currency'
                FROM orders AS o
                JOIN quotes AS q ON q.quote_id = o.quote_id AND q.company_id = o.company_id
                WHERE o.company_id = %s AND o.order_id = %s
                """,
                (company_id, order_id),
            )
            order = await cursor.fetchone()
            if order is None:
                raise OrderNotFoundError(order_id)
            await cursor.execute(
                """
                SELECT quote_revision_id, revision_number, revision_status, discount_rate
                FROM quote_revisions
                WHERE quote_id = %s AND revision_status = 'Approved'
                ORDER BY revision_number DESC
                LIMIT 1
                """,
                (order[1],),
            )
            revision = await cursor.fetchone()
            await cursor.execute(
                """
                SELECT order_line_id, fulfillment_status
                FROM order_lines
                WHERE order_id = %s
                ORDER BY order_line_id
                """,
                (order_id,),
            )
            fulfillment_rows = await cursor.fetchall()
            line_rows: list[tuple[Any, ...]] = []
            if revision is not None:
                await cursor.execute(
                    """
                    SELECT quote_line_id, machine_id, source_data ->> 'description', price
                    FROM quote_lines
                    WHERE quote_revision_id = %s
                    ORDER BY quote_line_id
                    """,
                    (revision[0],),
                )
                line_rows = await cursor.fetchall()

    return {
        "order_id": order[0], "quote_id": order[1], "order_status": order[2],
        "shipment_status": order[3], "currency": order[4],
        "approved_revision": None if revision is None else {
            "revision_number": revision[1], "revision_status": revision[2], "discount_rate": revision[3],
        },
        "items": [
            {"quote_line_id": row[0], "machine_id": row[1], "description": row[2], "price": row[3]}
            for row in line_rows
        ],
        "fulfillment": [{"order_line_id": row[0], "fulfillment_status": row[1]} for row in fulfillment_rows],
    }

async def get_company_quotes(company_id: str, limit: int) -> list[dict[str, Any]]:
    """Compatibility list for an already-authorised company."""
    return (await search_company_commercial(company_id, "quotes", limit))["items"]

async def search_company_commercial(
    company_id: str, kind: str, limit: int, **filters: Any,
) -> dict[str, Any]:
    """Count and select filtered documents in one PostgreSQL statement/snapshot.

    Machine filters select documents, never remove lines from their totals.
    Orders use the highest approved revision; quotes use the current revision.
    Caller must authorise commercial access before invoking this function.
    """
    if kind not in {"orders", "quotes"}:
        raise ValueError("Unsupported commercial document kind.")
    is_order = kind == "orders"
    alias = "o" if is_order else "q"
    fields = (["order_id", "quote_id", "order_status", "shipment_status", "currency", "order_date"]
              if is_order else ["quote_id", "valid_until", "revision_number", "revision_status",
                                "discount_rate", "line_total", "currency", "created_at"])
    clauses = [f"{alias}.company_id = %s"]
    parameters: list[Any] = [company_id]
    columns = ({"order_id": "o.order_id", "quote_id": "o.quote_id",
                "order_status": "o.order_status", "shipment_status": "o.shipment_status"}
               if is_order else {"quote_id": "q.quote_id", "revision_status": "qr.revision_status"})
    for name, column in columns.items():
        if filters.get(name) is not None:
            clauses.append(f"{column} = %s")
            parameters.append(filters[name])
    date_field = "order_date" if is_order else "created_at"
    for name, operator in (("start_date", ">="), ("end_date", "<=")):
        if filters.get(name) is not None:
            clauses.append(f"NULLIF({alias}.source_data ->> '{date_field}', '')::date {operator} %s")
            parameters.append(filters[name])
    if filters.get("machine_id") is not None:
        clauses.append("""EXISTS (
            SELECT 1 FROM quote_lines AS ml
            JOIN machines AS m ON m.machine_id = ml.machine_id
            WHERE ml.quote_revision_id = qr.quote_revision_id
              AND ml.machine_id = %s AND m.company_id = %s
        )""")
        parameters.extend([filters["machine_id"], company_id])
    where_sql = " AND ".join(clauses)
    if is_order:
        selection = """o.order_id, o.quote_id, o.order_status, o.shipment_status,
            o.source_data ->> 'currency' AS currency,
            NULLIF(o.source_data ->> 'order_date', '')::date AS order_date"""
        source = """orders AS o LEFT JOIN LATERAL (
            SELECT r.quote_revision_id FROM quote_revisions AS r
            JOIN quotes AS q ON q.quote_id = r.quote_id AND q.company_id = o.company_id
            WHERE r.quote_id = o.quote_id AND r.revision_status = 'Approved'
            ORDER BY r.revision_number DESC LIMIT 1
        ) AS qr ON TRUE"""
    else:
        selection = """q.quote_id, q.valid_until, qr.revision_number, qr.revision_status,
            qr.discount_rate, COALESCE((SELECT SUM(price) FROM quote_lines
                WHERE quote_revision_id = qr.quote_revision_id), 0) AS line_total,
            q.source_data ->> 'currency' AS currency,
            NULLIF(q.source_data ->> 'created_at', '')::date AS created_at"""
        source = """quotes AS q LEFT JOIN LATERAL (
            SELECT quote_revision_id, revision_number, revision_status, discount_rate
            FROM quote_revisions WHERE quote_id = q.quote_id
            ORDER BY revision_number DESC LIMIT 1
        ) AS qr ON TRUE"""
    selected_fields = ", ".join(f"page.{field}" for field in fields)
    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"""WITH filtered AS (
                    SELECT {selection} FROM {source} WHERE {where_sql}
                )
                SELECT totals.total_count, {selected_fields}
                FROM (SELECT COUNT(*) AS total_count FROM filtered) AS totals
                LEFT JOIN LATERAL (
                    SELECT * FROM filtered ORDER BY {fields[0]} DESC LIMIT %s
                ) AS page ON TRUE
                ORDER BY page.{fields[0]} DESC""",
                (*parameters, limit),
            )
            rows = await cursor.fetchall()
    total = int(rows[0][0])
    items = [dict(zip(fields, row[1:])) for row in rows if row[1] is not None]
    if not is_order:
        for item in items:
            item["validity_status"] = quote_validity_status(item["valid_until"])
    return {"items": items, "total_count": total, "returned_count": len(items),
            "is_truncated": total > len(items), "limit": limit, "filters": filters,
            "company_id": company_id, "date_field": date_field}

def _line_key(line: dict[str, Any]) -> tuple[str, str]:
    """Match by machine and normalised description; this is not a stable line ID."""

    return (str(line["machine_id"] or ""), str(line["description"] or "").casefold().strip())

def _compare_quote_lines(
    previous_lines: list[dict[str, Any]],
    current_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Describe line additions, removals and net-price changes across revisions."""

    previous_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    current_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for line in previous_lines:
        previous_by_key.setdefault(_line_key(line), []).append(line)
    for line in current_lines:
        current_by_key.setdefault(_line_key(line), []).append(line)
    changes: list[dict[str, Any]] = []
    for key in sorted(set(previous_by_key) | set(current_by_key)):
        previous_group = previous_by_key.get(key, [])
        current_group = current_by_key.get(key, [])
        if len(previous_group) > 1 or len(current_group) > 1:
            changes.append({
                "change": "ambiguous", "machine_id": key[0] or None,
                "description": (current_group or previous_group)[0]["description"],
                "previous_price": None, "current_price": None,
                "previous_lines": previous_group, "current_lines": current_group,
            })
            continue
        previous = previous_group[0] if previous_group else None
        current = current_group[0] if current_group else None
        reference = current or previous
        assert reference is not None
        if previous is None:
            change = "added"
        elif current is None:
            change = "removed"
        elif previous["price"] != current["price"]:
            change = "price_changed"
        else:
            continue
        changes.append(
            {
                "change": change,
                "machine_id": reference["machine_id"],
                "description": reference["description"],
                "previous_price": None if previous is None else previous["price"],
                "current_price": None if current is None else current["price"],
            }
        )
    return changes

async def get_company_quote_history(company_id: str, quote_id: str) -> dict[str, Any]:
    """Return one company's full quote history and the latest revision comparison."""

    async with connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT quote_id, valid_until, source_data ->> 'currency',
                       source_data ->> 'created_at', source_data ->> 'description'
                FROM quotes
                WHERE quote_id = %s AND company_id = %s
                """,
                (quote_id, company_id),
            )
            quote = await cursor.fetchone()
            if quote is None:
                raise QuoteNotFoundError(quote_id)
            await cursor.execute(
                """
                SELECT qr.quote_revision_id, qr.revision_number, qr.revision_status,
                       qr.discount_rate, qr.source_data ->> 'issued_at',
                       qr.source_data ->> 'change_summary',
                       COALESCE(SUM(ql.price), 0) AS line_total
                FROM quote_revisions AS qr
                LEFT JOIN quote_lines AS ql ON ql.quote_revision_id = qr.quote_revision_id
                WHERE qr.quote_id = %s
                GROUP BY qr.quote_revision_id, qr.revision_number, qr.revision_status,
                         qr.discount_rate, qr.source_data
                ORDER BY qr.revision_number
                """,
                (quote_id,),
            )
            revision_rows = await cursor.fetchall()
            await cursor.execute(
                """
                SELECT ql.quote_revision_id, ql.quote_line_id, ql.machine_id, ql.price,
                       ql.source_data ->> 'description'
                FROM quote_lines AS ql
                JOIN quote_revisions AS qr ON qr.quote_revision_id = ql.quote_revision_id
                WHERE qr.quote_id = %s
                ORDER BY ql.quote_revision_id, ql.quote_line_id
                """,
                (quote_id,),
            )
            line_rows = await cursor.fetchall()

    lines_by_revision: dict[str, list[dict[str, Any]]] = {}
    for row in line_rows:
        lines_by_revision.setdefault(row[0], []).append(
            {
                "quote_line_id": row[1],
                "machine_id": row[2],
                "price": row[3],
                "description": row[4],
            }
        )
    revisions = [
        {
            "quote_revision_id": row[0],
            "revision_number": row[1],
            "revision_status": row[2],
            "discount_rate": row[3],
            "issued_at": row[4],
            "change_summary": row[5],
            "line_total": row[6],
            "lines": lines_by_revision.get(row[0], []),
        }
        for row in revision_rows
    ]
    comparison = []
    if len(revisions) >= 2:
        comparison = _compare_quote_lines(revisions[-2]["lines"], revisions[-1]["lines"])
    return {
        "quote_id": quote[0],
        "valid_until": quote[1],
        "validity_status": quote_validity_status(quote[1]),
        "currency": quote[2],
        "created_at": quote[3],
        "description": quote[4],
        "revisions": revisions,
        "latest_comparison": comparison,
        "comparison_basis": (
            "Calculated by machine_id and normalised description, not a stable line identifier. "
            "Description changes appear as removed and added lines; duplicate keys are ambiguous. "
            "Source change_summary is returned separately for each revision."
        ),
    }
