from __future__ import annotations

from functools import lru_cache
from typing import List, Optional, Tuple

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


def list_call_logs(
    limit: Optional[int] = None,
    offset: int = 0,
    order_desc: bool = True,
) -> Tuple[List[dict], Optional[int]]:
    settings = get_settings()
    query = (
        get_supabase_client()
        .table(settings.supabase_call_metrics_table)
        .select("*", count="exact")
        .order("call_started_at", desc=order_desc)
    )
    if limit is not None:
        start = max(offset, 0)
        end = start + max(limit, 0) - 1
        query = query.range(start, end)
    response = query.execute()
    if getattr(response, "error", None):
        raise RuntimeError(response.error)
    data = getattr(response, "data", []) or []
    total = getattr(response, "count", None)
    return data, total


def fetch_call_logs(limit: Optional[int] = None) -> List[dict]:
    data, _ = list_call_logs(limit=limit)
    return data


def create_call_log(payload: dict) -> dict:
    settings = get_settings()
    response = (
        get_supabase_client()
        .table(settings.supabase_call_metrics_table)
        .insert(payload)
        .execute()
    )
    if getattr(response, "error", None):
        raise RuntimeError(response.error)
    data = getattr(response, "data", []) or []
    return data[0] if data else {}


# def update_call_log(call_id: str, payload: dict) -> Optional[dict]:
#     settings = get_settings()
#     response = (
#         get_supabase_client()
#         .table(settings.supabase_call_metrics_table)
#         .update(payload)
#         .eq("call_id", call_id)
#         .execute()
#     )
#     if getattr(response, "error", None):
#         raise RuntimeError(response.error)
#     data = getattr(response, "data", []) or []
#     return data[0] if data else None


# def delete_call_log(call_id: str) -> bool:
#     settings = get_settings()
#     response = (
#         get_supabase_client()
#         .table(settings.supabase_call_metrics_table)
#         .delete()
#         .eq("call_id", call_id)
#         .select("call_id")
#         .execute()
#     )
#     if getattr(response, "error", None):
#         raise RuntimeError(response.error)
#     data = getattr(response, "data", []) or []
#     return bool(data)


def get_call_log(call_id: str) -> Optional[dict]:
    settings = get_settings()
    response = (
        get_supabase_client()
        .table(settings.supabase_call_metrics_table)
        .select("*")
        .eq("call_id", call_id)
        .limit(1)
        .execute()
    )
    if getattr(response, "error", None):
        raise RuntimeError(response.error)
    data = getattr(response, "data", []) or []
    return data[0] if data else None


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
    """Update the load_booked field for a given load_id."""
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
