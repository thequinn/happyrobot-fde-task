from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class Load(BaseModel):
    load_id: str
    load_booked: Optional[str] = None
    origin: str
    destination: str
    pickup_datetime: Optional[datetime] = None
    delivery_datetime: Optional[datetime] = None
    equipment_type: str
    loadboard_rate: Optional[float] = None
    notes: Optional[str] = None
    weight: Optional[int] = None
    commodity_type: Optional[str] = None
    num_of_pieces: Optional[int] = None
    miles: Optional[int] = None
    dimensions: Optional[str] = None


# class NegotiationResponse(BaseModel):
#     load_id: str
#     load_booked: str
#     carrier_offer: int
#     agent_new_offer: int
#     agreed_price: int  # -1 means no agreement reached
#     message: str
#     remaining_attempts: int = 3


class LoadListResponse(BaseModel):
    data: List[Load]


class CallLog(BaseModel):
    call_id: Optional[str] = None
    load_id: str
    call_started_at: datetime
    sentiment: str
    outcome: str


class CallLogCreate(BaseModel):
    load_id: str
    call_started_at: datetime
    sentiment: str
    outcome: str


class CallLogUpdate(BaseModel):
    load_id: Optional[str] = None
    call_started_at: Optional[datetime] = None
    sentiment: Optional[str] = None
    outcome: Optional[str] = None


class CallLogListResponse(BaseModel):
    data: List[CallLog]
    total: Optional[int] = None


class CallMetricsSummary(BaseModel):
    total_calls: int
    sentiment_distribution: Dict[str, int]
    outcome_breakdown: Dict[str, int]


__all__ = [
    "Load",
    "LoadListResponse",
    # "NegotiationResponse",
    "CallLog",
    "CallLogCreate",
    "CallLogUpdate",
    "CallLogListResponse",
    "CallMetricsSummary",
]
