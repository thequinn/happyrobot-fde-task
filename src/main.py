from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import APIKeyHeader
from pydantic import AnyHttpUrl, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from supabase import Client, create_client
import httpx


# Set up basic configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Example usage
logger.info("This is an info message.")


class Settings(BaseSettings):
    """Application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    supabase_url: AnyHttpUrl = Field(alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    api_auth_key: str = Field(alias="LOAD_API_KEY")
    supabase_table: str = Field(default="loads", alias="SUPABASE_LOADS_TABLE")


class Load(BaseModel):
    load_id: str
    load_booked: Optional[str] = None
    counter_offer: Optional[float] = None
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
    counter_offer: Optional[float] = None
    message: str
    remaining_attempts: int = 0


app = FastAPI(
    title="Load Search API",
    description="Search freight loads stored in Supabase using origin, destination, and equipment filters.",
    version="0.1.0",
)


api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

# Maximum number of negotiation attempts per load
MAX_NEGOTIATION_EXCHANGES = 3


# In-memory state per load_id tracking attempts and latest agent offer
@dataclass
class NegotiationState:
    attempts: int = 0
    last_agent_offer: Optional[float] = None


NEGOTIATION_STATE: dict[str, NegotiationState] = {}


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    # Create client with default options
    return create_client(str(settings.supabase_url), settings.supabase_service_role_key)


async def enforce_api_key(authorization: str = Depends(api_key_header)) -> None:
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
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
        )


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/get_loads", response_model=List[Load], dependencies=[Depends(enforce_api_key)]
)
async def get_loads(origin: str, destination: str, equipment_type: str) -> List[Load]:
    settings = get_settings()
    supabase = get_supabase_client()

    logger.info(
        "Querying Supabase for loads matching %s, %s, %s",
        origin,
        destination,
        equipment_type,
    )

    # Select a specific table to query, and then select all columns
    query = supabase.table(settings.supabase_table).select("*")

    # The chained ilike() calls function as an AND operation.  This is equivalent to an SQL WHERE clause with multiple conditions
    query = (
        query
        # Filter by origin, destination, and equipment type
        .ilike("origin", f"%{origin}%")
        .ilike("destination", f"%{destination}%")
        .ilike("equipment_type", f"%{equipment_type}%")
    )

    try:
        response = query.execute()
    except Exception as exc:
        logger.exception("Supabase query failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to query data store"
        ) from exc

    if getattr(response, "error", None):
        logger.error("Supabase returned error: %s", response.error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error returned by data store",
        )

    data = getattr(response, "data", []) or []

    try:
        return [Load.model_validate(item) for item in data]
    except Exception as exc:
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
    """Return the agent's response and the offer he will carry forward."""

    agent_original_offer = (
        load.loadboard_rate
        if load and load.loadboard_rate is not None
        else carrier_offer
    )

    if attempt_index == 0:
        agent_new_offer = round(agent_original_offer * 0.97)
    else:
        baseline = (
            agent_last_offer if agent_last_offer is not None else agent_original_offer
        )
        agent_new_offer = round((agent_original_offer + baseline) / 2.0)

    if carrier_offer >= agent_new_offer:
        message = (
            f"The agent accepted the carrier's offer of ${carrier_offer:,.0f}; "
            f"it meets the agent's target of ${agent_new_offer:,.0f}."
        )
        response = NegotiationResponse(
            load_id=load_id,
            load_booked="Y",
            message=message,
        )
    else:
        message = (
            f"The agent counters at ${agent_new_offer:,.0f}. "
            f"Original ask was ${agent_original_offer:,.0f}."
        )
        response = NegotiationResponse(
            load_id=load_id,
            load_booked="N",
            counter_offer=float(agent_new_offer),
            message=message,
        )

    return response, float(agent_new_offer)


# The param,dependencies, forces API key authentication on every call to /negotiate
@app.post(
    "/negotiate",
    response_model=NegotiationResponse,
    dependencies=[Depends(enforce_api_key)],
)
async def negotiate(
    load_id: str, carrier_offer: float, notes: Optional[str] = None
) -> NegotiationResponse:
    settings = get_settings()
    supabase = get_supabase_client()

    state = NEGOTIATION_STATE.get(load_id)
    if state is None:
        state = NegotiationState()
        NEGOTIATION_STATE[load_id] = state

    if state.attempts >= MAX_NEGOTIATION_EXCHANGES:
        return NegotiationResponse(
            load_id=load_id,
            load_booked="N",
            message="Negotiation attempt limit reached; please contact support.",
            remaining_attempts=0,
        )

    try:
        response = (
            supabase.table(settings.supabase_table)
            .select("*")
            .eq("load_id", load_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.exception("Supabase lookup for negotiation failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to query data store",
        ) from exc

    if getattr(response, "error", None):
        logger.error("Supabase returned error during negotiation: %s", response.error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error returned by data store",
        )

    records = getattr(response, "data", []) or []
    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Load not found"
        )

    try:
        load = Load.model_validate(records[0])
    except Exception as exc:
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
    elif remaining_attempts <= 0:
        state.attempts = MAX_NEGOTIATION_EXCHANGES
        negotiation_response.message += " No further counter offers are available."

    return negotiation_response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
