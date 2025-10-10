from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from ..db import fetch_loads
from ..models import Load, LoadListResponse
from ..security import enforce_api_key


logger = logging.getLogger(__name__)

router = APIRouter(tags=["loads"], dependencies=[Depends(enforce_api_key)])


@router.get("/get_loads", response_model=LoadListResponse)
async def get_loads(
    origin: str, destination: str, equipment_type: str
) -> LoadListResponse:
    try:
        payload = fetch_loads(origin, destination, equipment_type)

    except RuntimeError as exc:
        logger.exception("Supabase query failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to query data store",
        ) from exc

    try:
        booked_only = [item for item in payload if item.get("load_booked") == "N"]
        loads = [Load.model_validate(item) for item in booked_only]

        tmp = LoadListResponse(data=loads)
        return tmp

    except Exception as exc:  # pragma: no cover - defensive data validation
        logger.exception("Failed to validate load payload from Supabase")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid data in data store",
        ) from exc


__all__ = ["router"]
