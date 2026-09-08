"""Manuals API endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from agents.manuals import ManualsUnavailableError, can_open_file, search as search_manual
from api.presenters import manual_search_result
from api.schemas import ManualSearchResult
from core.auth import AuthContext, get_current_user
from db.repositories.errors import MachineNotFoundError


MANUALS_DIRECTORY = Path("/data/manuals")

router = APIRouter()

@router.get("/machines/{machine_id}/manuals/search", response_model=list[ManualSearchResult])
async def search_machine_manual(
    machine_id: str,
    query: str = Query(min_length=1, max_length=1_000),
    user: AuthContext = Depends(get_current_user),
    limit: int = Query(default=5, ge=1, le=10),
) -> list[ManualSearchResult]:
    """Manuals Agent endpoint: semantic search scoped to one authorised machine."""

    normalized_query = query.strip()
    if not normalized_query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The manual search query cannot be blank.",
        )
    try:
        rows = await search_manual(machine_id.strip(), normalized_query, user, limit)
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    except ManualsUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Manual search is temporarily unavailable.",
        ) from error
    return [manual_search_result(row) for row in rows]

@router.get("/machines/{machine_id}/manuals/files/{source_file}")
async def open_machine_manual(
    machine_id: str,
    source_file: str,
    user: AuthContext = Depends(get_current_user),
) -> FileResponse:
    """Serve one authorised local manual inline; it is never a public static file."""

    safe_file_name = Path(source_file).name
    if safe_file_name != source_file or Path(safe_file_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found.")

    try:
        is_available = await can_open_file(machine_id.strip(), safe_file_name, user)
    except MachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found.",
        ) from error
    if not is_available:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found.")

    manual_path = MANUALS_DIRECTORY / safe_file_name
    if not manual_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual file is unavailable.")
    return FileResponse(
        manual_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_file_name}"'},
    )
