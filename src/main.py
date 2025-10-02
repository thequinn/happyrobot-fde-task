from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache
from typing import List, Optional, Union

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import APIKeyHeader
from pydantic import AnyHttpUrl, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from supabase import Client, create_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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


app = FastAPI(
    title="Load Search API",
    description="Search freight loads stored in Supabase using origin, destination, and equipment filters.",
    version="0.1.0",
)


api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
