from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import Response

from ..db import (
    create_call_log,
    delete_call_log,
    get_call_log,
    list_call_logs,
    update_call_log,
)
from ..models import CallLog, CallLogCreate, CallLogListResponse, CallLogUpdate
from ..security import enforce_api_key


logger = logging.getLogger(__name__)

router = APIRouter(tags=["call_logs"], dependencies=[Depends(enforce_api_key)])


@router.post("/call_logs", response_model=CallLog, status_code=status.HTTP_201_CREATED)
async def create_call_log_entry(payload: CallLogCreate) -> CallLog:
    # Persist the call log in Supabase using JSON-friendly values (dates -> ISO strings).
    try:
        record = create_call_log(payload.model_dump(mode="json"))
    except RuntimeError as exc:
        logger.exception("Supabase insert failed for call_logs")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create call log record",
        ) from exc

    if not record:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Call log created but response was empty",
        )

    try:
        return CallLog.model_validate(record)
    except Exception as exc:  # pragma: no cover - defensive data validation
        logger.exception("Invalid call log payload returned from Supabase")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid call log payload in data store",
        ) from exc


@router.get("/call_logs", response_model=CallLogListResponse)
async def list_call_log_entries(
    limit: int = Query(50, ge=1, le=500, description="Maximum number of call logs."),
    offset: int = Query(0, ge=0, description="Number of records to skip."),
) -> CallLogListResponse:
    # Fetch a paginated slice from Supabase; FastAPI handles query param parsing.
    try:
        records, total = list_call_logs(limit=limit, offset=offset)
    except RuntimeError as exc:
        logger.exception("Supabase query failed for call_logs list")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve call logs",
        ) from exc

    call_logs: list[CallLog] = []
    for record in records:
        try:
            call_logs.append(CallLog.model_validate(record))
        except Exception:
            logger.warning("Skipping invalid call log record: %s", record)

    return CallLogListResponse(data=call_logs, total=total)


@router.get(
    "/call_logs/{call_id}",
    response_model=CallLog,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Call log not found"}},
)
async def get_call_log_entry(
    call_id: str = Path(..., description="Identifier of the call log"),
) -> CallLog:
    # Look up a single call log, returning 404 if Supabase has no match.
    try:
        record = get_call_log(call_id)
    except RuntimeError as exc:
        logger.exception("Supabase lookup failed for call_logs")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve call log",
        ) from exc

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call log not found",
        )

    try:
        return CallLog.model_validate(record)
    except Exception as exc:  # pragma: no cover - defensive data validation
        logger.exception("Invalid call log payload returned from Supabase")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid call log payload in data store",
        ) from exc


@router.patch(
    "/call_logs/{call_id}",
    response_model=CallLog,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Call log not found"}},
)
async def update_call_log_entry(
    call_id: str,
    payload: CallLogUpdate,
) -> CallLog:
    # Apply partial updates from the agent, guarding against empty payloads.
    updates = payload.model_dump(exclude_unset=True, mode="json")
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided to update",
        )

    try:
        record = update_call_log(call_id, updates)
    except RuntimeError as exc:
        logger.exception("Supabase update failed for call_logs")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Failed to update call log",
        ) from exc

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call log not found",
        )

    try:
        return CallLog.model_validate(record)
    except Exception as exc:  # pragma: no cover - defensive data validation
        logger.exception("Invalid call log payload returned from Supabase")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid call log payload in data store",
        ) from exc


@router.delete(
    "/call_logs/{call_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Call log not found"},
        status.HTTP_502_BAD_GATEWAY: {
            "description": "Failed to delete call log due to upstream error"
        },
    },
)
async def delete_call_log_entry(call_id: str) -> Response:
    # Remove the call log and return an empty 204 response on success.
    try:
        deleted = delete_call_log(call_id)
    except RuntimeError as exc:
        logger.exception("Supabase delete failed for call_logs")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Failed to delete call log",
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call log not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
