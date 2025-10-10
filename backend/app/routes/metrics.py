from __future__ import annotations

import logging
from collections import Counter
from typing import Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..db import fetch_call_logs
from ..models import CallLog, CallMetricsSummary
from ..security import enforce_api_key


logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"], dependencies=[Depends(enforce_api_key)])


def _normalize_distribution(values: Iterable[Optional[str]]) -> dict[str, int]:
    normalized: list[Optional[str]] = []
    for value in values:
        if value is None:
            normalized.append(None)
            continue
        trimmed = value.strip()
        normalized.append(trimmed.lower() if trimmed else None)

    counter = Counter(item for item in normalized if item is not None)
    unspecified = sum(1 for item in normalized if item is None)
    if unspecified:
        counter["unspecified"] = counter.get("unspecified", 0) + unspecified
    return dict(counter)


@router.get("/metrics/summary", response_model=CallMetricsSummary)
async def get_metrics_summary(
    limit: int | None = Query(
        default=None,
        ge=1,
        le=10000,
        description=(
            "Optional limit on number of call records to aggregate. "
            "If omitted, aggregates across all available records."
        ),
    )
) -> CallMetricsSummary:
    try:
        payload = fetch_call_logs(limit=limit)
    except RuntimeError as exc:
        logger.exception("Supabase query for call metrics failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to query call metrics",
        ) from exc

    if not payload:
        return CallMetricsSummary(
            total_calls=0,
            sentiment_distribution={},
            outcome_breakdown={},
        )

    call_logs: list[CallLog] = []
    print("\nmetrics.py, payload:\n", payload)
    for record in payload:
        try:
            call_logs.append(CallLog.model_validate(record))
        except Exception:
            logger.warning("Dropping invalid call metrics record: %s", record)

    if not call_logs:
        return CallMetricsSummary(
            total_calls=0,
            sentiment_distribution={},
            outcome_breakdown={},
        )

    sentiment_distribution = _normalize_distribution(log.sentiment for log in call_logs)
    outcome_distribution = _normalize_distribution(log.outcome for log in call_logs)

    return CallMetricsSummary(
        total_calls=len(call_logs),
        sentiment_distribution=sentiment_distribution,
        outcome_breakdown=outcome_distribution,
    )


__all__ = ["router"]
