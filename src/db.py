from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from supabase import Client, create_client

from .config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(str(settings.supabase_url), settings.supabase_service_role_key)


def fetch_loads(
    origin: str,
    destination: str,
    equipment_type: str,
) -> List[dict]:
    settings = get_settings()
    query = get_supabase_client().table(settings.supabase_table).select("*")
    query = (
        query.ilike("origin", f"%{origin}%")
        .ilike("destination", f"%{destination}%")
        .ilike("equipment_type", f"%{equipment_type}%")
    )
    response = query.execute()
    if getattr(response, "error", None):
        raise RuntimeError(response.error)
    return getattr(response, "data", []) or []


def fetch_load(load_id: str) -> Optional[dict]:
    settings = get_settings()
    response = (
        get_supabase_client()
        .table(settings.supabase_table)
        .select("*")
        .eq("load_id", load_id)
        .limit(1)
        .execute()
    )
    if getattr(response, "error", None):
        raise RuntimeError(response.error)
    data = getattr(response, "data", []) or []
    return data[0] if data else None


def update_load_booked(load_id: str, booked_value: str) -> None:
    settings = get_settings()
    response = (
        get_supabase_client()
        .table(settings.supabase_table)
        .update({"load_booked": booked_value})
        .eq("load_id", load_id)
        .execute()
    )
    if getattr(response, "error", None):
        raise RuntimeError(response.error)
