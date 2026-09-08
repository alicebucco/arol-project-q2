"""Shared HTTP metadata for truncated list responses."""

from typing import Any

from fastapi import Response


def _list_headers(response: Response, result: dict[str, Any]) -> None:
    """Keep list response bodies compatible while exposing completeness."""
    response.headers["X-Total-Count"] = str(result["total_count"])
    response.headers["X-Returned-Count"] = str(result["returned_count"])
    response.headers["X-Is-Truncated"] = str(result["is_truncated"]).lower()
    response.headers["X-Limit"] = str(result["limit"])
