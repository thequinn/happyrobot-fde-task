from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# PROJECT_ROOT is computed by taking the current file (e.g., backend/app/config.py), resolving it to an absolute path, and stepping up two levels (/backend/app → /backend).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: AnyHttpUrl = Field(alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    api_auth_key: str = Field(alias="LOAD_API_KEY")
    supabase_table: str = Field(default="loads", alias="SUPABASE_LOADS_TABLE")
    supabase_call_metrics_table: str = Field(
        default="call_metrics", alias="SUPABASE_CALL_METRICS_TABLE"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
