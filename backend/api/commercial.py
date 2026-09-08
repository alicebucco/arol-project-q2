"""Commercial API endpoints."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from agents.orders import order_detail, quote_history, search_orders, search_quotes
from api.pagination import _list_headers
from api.schemas import ApprovedOrderRevision, FulfillmentLine, OrderDetail, OrderItem, OrderRecord, QuoteHistory, QuoteLineChange, QuoteLineDetail, QuoteRecord, QuoteRevisionDetail
from core.auth import AuthContext, get_current_user
from db.repositories.errors import OrderNotFoundError, QuoteNotFoundError

router = APIRouter()

@router.get("/orders", response_model=list[OrderRecord])
async def company_orders(
    response: Response,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    machine_id: str | None = None,
    order_id: str | None = None,
    quote_id: str | None = None,
    order_status: str | None = None,
    shipment_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[OrderRecord]:
    """Orders Agent endpoint; company scope comes from the authenticated user."""

    try:
        result = await search_orders(
            user, limit, machine_id=machine_id, order_id=order_id, quote_id=quote_id,
            order_status=order_status, shipment_status=shipment_status,
            start_date=start_date, end_date=end_date,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    _list_headers(response, result)
    rows = result["items"]
    return [OrderRecord(**row) for row in rows]

@router.get("/orders/{order_id}", response_model=OrderDetail)
async def company_order_detail(order_id: str, user: AuthContext = Depends(get_current_user)) -> OrderDetail:
    """Return the approved quote content and fulfilment status of one order."""

    try:
        detail = await order_detail(user, order_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OrderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.") from error
    revision = detail["approved_revision"]
    return OrderDetail(
        order_id=detail["order_id"], quote_id=detail["quote_id"], order_status=detail["order_status"],
        shipment_status=detail["shipment_status"], currency=detail["currency"],
        approved_revision=None if revision is None else ApprovedOrderRevision(
            revision_number=revision["revision_number"], revision_status=revision["revision_status"],
            discount_rate=float(revision["discount_rate"]) if revision["discount_rate"] is not None else None,
        ),
        items=[OrderItem(price=float(item["price"]), **{key: value for key, value in item.items() if key != "price"}) for item in detail["items"]],
        fulfillment=[FulfillmentLine(**line) for line in detail["fulfillment"]],
    )

@router.get("/quotes", response_model=list[QuoteRecord])
async def company_quotes(
    response: Response,
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    machine_id: str | None = None,
    quote_id: str | None = None,
    revision_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[QuoteRecord]:
    """Orders Agent endpoint for latest quote revisions and totals."""

    try:
        result = await search_quotes(
            user, limit, machine_id=machine_id, quote_id=quote_id,
            revision_status=revision_status, start_date=start_date, end_date=end_date,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    _list_headers(response, result)
    rows = result["items"]
    return [
        QuoteRecord(
            valid_until=row["valid_until"].isoformat() if row["valid_until"] else None,
            validity_status=row["validity_status"],
            discount_rate=float(row["discount_rate"]) if row["discount_rate"] is not None else None,
            line_total=float(row["line_total"]),
            **{
                key: value
                for key, value in row.items()
                if key not in {"valid_until", "validity_status", "discount_rate", "line_total"}
            },
        )
        for row in rows
    ]

@router.get("/quotes/{quote_id}", response_model=QuoteHistory)
async def company_quote_history(
    quote_id: str,
    user: AuthContext = Depends(get_current_user),
) -> QuoteHistory:
    """Return all authorised revisions, lines, and latest revision changes."""

    try:
        history = await quote_history(user, quote_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except QuoteNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found.",
        ) from error

    return QuoteHistory(
        valid_until=history["valid_until"].isoformat() if history["valid_until"] else None,
        validity_status=history["validity_status"],
        currency=history["currency"],
        created_at=history["created_at"],
        description=history["description"],
        quote_id=history["quote_id"],
        revisions=[
            QuoteRevisionDetail(
                discount_rate=float(revision["discount_rate"]) if revision["discount_rate"] is not None else None,
                line_total=float(revision["line_total"]),
                lines=[
                    QuoteLineDetail(price=float(line["price"]), **{key: value for key, value in line.items() if key != "price"})
                    for line in revision["lines"]
                ],
                **{
                    key: value
                    for key, value in revision.items()
                    if key not in {"discount_rate", "line_total", "lines"}
                },
            )
            for revision in history["revisions"]
        ],
        comparison_basis=history.get("comparison_basis"),
        latest_comparison=[
            QuoteLineChange(
                previous_price=float(change["previous_price"]) if change["previous_price"] is not None else None,
                current_price=float(change["current_price"]) if change["current_price"] is not None else None,
                **{key: value for key, value in change.items() if key not in {"previous_price", "current_price"}},
            )
            for change in history["latest_comparison"]
        ],
    )
