from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import inspect
import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from .config import get_settings
from .db import fetch_load, fetch_loads, update_load_booked


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Supabase's Python SDK still calls httpx.Client(proxy=...), but newer httpx
# releases removed that keyword. Patch the constructor so both styles work.
_httpx_signature = inspect.signature(httpx.Client.__init__)
if "proxy" not in _httpx_signature.parameters:
    _original_httpx_init = httpx.Client.__init__

    def _patched_httpx_init(self, *args, proxy=None, **kwargs):
        if proxy is not None and "proxies" not in kwargs:
            kwargs["proxies"] = proxy
        _original_httpx_init(self, *args, **kwargs)

    httpx.Client.__init__ = _patched_httpx_init


class Load(BaseModel):
    load_id: str
    load_booked: str
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


class NegotiationResponse(BaseModel):
    load_id: str
    load_booked: str
    carrier_offer: float
    agent_new_offer: float
    agreed_price: float  # -1 means no agreement reached
    message: str
    remaining_attempts: int = 3


app = FastAPI(
    title="Load Search API",
    description="Search freight loads stored in Supabase using origin, destination, and equipment filters.",
    version="0.1.0",
)

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)
MAX_NEGOTIATION_EXCHANGES = 3


@dataclass
class NegotiationState:
    attempts: int = 0
    last_agent_offer: Optional[float] = None


NEGOTIATION_STATE: dict[str, NegotiationState] = {}


def enforce_api_key(authorization: str = Depends(api_key_header)) -> None:
    settings = get_settings()
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )

    if token != settings.api_auth_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/get_loads", response_model=List[Load], dependencies=[Depends(enforce_api_key)]
)
async def get_loads(origin: str, destination: str, equipment_type: str) -> List[Load]:
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
        return [Load.model_validate(item) for item in booked_only]
    except Exception as exc:  # pragma: no cover - defensive data validation
        logger.exception("Failed to validate load payload from Supabase")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid data in data store",
        ) from exc


def run_negotiation_logic(
    load: Optional[Load],
    carrier_offer: float,
    load_id: str,
    attempt_index: int,
    agent_last_offer: Optional[float],
) -> tuple[NegotiationResponse, float]:

    # Round 0: This is the round before any negotiation.
    # Agent's original offer is the loadboard rate.
    agent_original_offer = (
        load.loadboard_rate
        if load and load.loadboard_rate is not None
        else carrier_offer
    )

    """
    agent_new_offer:

    (1) It is the threshold price agent can accept in the current round. It means if carrier_offer >= agent_new_offer, agent accepts the offer. 
    
    (2) If agent can't accept the carrier_offer, agent_new_offer will be used  as agent_last_offer in the next round.
    """
    # Round 1 of negotiation:
    if attempt_index == 0:
        agent_new_offer = round(agent_original_offer * 0.97)
    # Round 2 and 3 of negotiation
    else:
        # Add a random number to agent_new_offer, so it's not too predictable
        random_number = random.uniform(1, load.loadboard_rate * 0.02)
        agent_new_offer = round(
            (agent_original_offer + agent_last_offer + random_number) / 2.0
        )

    # Update agent_last_offer for next iteration
    agent_last_offer = agent_new_offer

    # If carrier_offer is greater than or equal to agent_new_offer, agent accepts the offer.
    if carrier_offer >= agent_new_offer:
        message = (
            f"The agent accepted the carrier's offer of ${carrier_offer:,.0f}; "
            f"it meets the agent's target of ${agent_new_offer:,.0f}."
        )
        response = NegotiationResponse(
            load_id=load_id,
            load_booked="Y",
            # Carrier's offer for this round
            carrier_offer=carrier_offer,
            # Agent doesn't need to counter cos agreen accepted carrier's proposed rate
            agent_new_offer=-1,
            agreed_price=carrier_offer,
            message=message,
            # Number of Carrier's counter offers
            # attempt_count=attempt_index + 1,
            remaining_attempts=0,
        )
    # If carrier_offer is less than agent_new_offer, agent counters.
    else:
        message = (
            f"The agent counters at ${agent_new_offer:,.0f}. "
            f"Original ask was ${agent_original_offer:,.0f}."
        )
        response = NegotiationResponse(
            load_id=load_id,
            load_booked="N",
            # Carrier's offer for this round
            carrier_offer=carrier_offer,
            # Agent's counter offer for next round
            agent_new_offer=agent_new_offer,
            # -1 means agent accepted the offer
            agreed_price=-1,
            message=message,
            # Number of Carrier's counter offers
            # attempt_count=attempt_index + 1,
            remaining_attempts=MAX_NEGOTIATION_EXCHANGES - attempt_index - 1,
        )

    return response, float(agent_new_offer)


@app.post(
    "/negotiate",
    response_model=NegotiationResponse,
    dependencies=[Depends(enforce_api_key)],
)
async def negotiate(
    load_id: str, carrier_offer: float, notes: Optional[str] = None
) -> NegotiationResponse:

    state = NEGOTIATION_STATE.get(load_id)
    if state is None:
        state = NegotiationState()
        NEGOTIATION_STATE[load_id] = state

    if state.attempts >= MAX_NEGOTIATION_EXCHANGES:
        response = NegotiationResponse(
            load_id=load_id,
            load_booked="N",
            # Carrier's offer for this round
            carrier_offer=carrier_offer,
            # -1  means max negotiation rounds exceends. Agent doesn't counter.
            agent_new_offer=-1,
            agreed_price=carrier_offer,
            message="Negotiation attempt limit reached; Please call again.",
            # Number of Carrier's counter offers
            # attempt_count=attempt_index + 1,
        )
        return response

    try:
        record = fetch_load(load_id)
    except RuntimeError as exc:
        logger.exception("Supabase lookup for negotiation failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to query data store",
        ) from exc

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Load not found",
        )

    try:
        load = Load.model_validate(record)
    except Exception as exc:  # pragma: no cover - defensive data validation
        logger.exception("Failed to validate load payload during negotiation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid data in data store",
        ) from exc

    negotiation_response, agent_offer = run_negotiation_logic(
        load,
        carrier_offer,
        load_id,
        state.attempts,
        state.last_agent_offer,
    )

    state.last_agent_offer = agent_offer
    state.attempts += 1
    remaining_attempts = MAX_NEGOTIATION_EXCHANGES - state.attempts
    negotiation_response.remaining_attempts = max(remaining_attempts, 0)

    if negotiation_response.load_booked == "Y":
        NEGOTIATION_STATE.pop(load_id, None)
        try:
            update_load_booked(load_id, "Y")
        except RuntimeError as exc:
            logger.exception("Failed to mark load as booked")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to update booking state",
            ) from exc
    elif remaining_attempts <= 0:
        state.attempts = MAX_NEGOTIATION_EXCHANGES
        negotiation_response.message += " No further counter offers are available."

    return negotiation_response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
