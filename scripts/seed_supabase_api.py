"""Seed or reseed the Supabase loads table from loads.json using Supabase API.

This is an alternative to seed_supabase.py that uses the Supabase client library
instead of direct database connections, which may be more reliable when
direct database access is restricted.

Steps:
1. Ensure the target table exists (create if missing).
2. Clear existing data if table exists.
3. Insert rows from the JSON seed file using Supabase client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv
from supabase import create_client, Client

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / "loads.json"
ENV_PATH = BASE_DIR / ".env"

if load_dotenv(ENV_PATH):
    print("Loaded environment variables from .env file")

try:
    SUPABASE_URL = os.environ["SUPABASE_URL"]
    SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
except KeyError as exc:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in your environment or .env file"
    ) from exc

TABLE_NAME = os.getenv("SUPABASE_LOADS_TABLE", "loads")


def load_seed_data(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as json_file:
        payload = json.load(json_file)
    if not isinstance(payload, list):
        raise ValueError("Seed data must be a list of load objects")
    normalized: list[dict[str, object]] = []
    for item in payload:
        record = dict(item)
        record.setdefault("load_booked", "Y")
        record.setdefault("counter_offer", None)
        normalized.append(record)
    return normalized


def clear_table(supabase: Client) -> None:
    """Clear all data from the loads table."""
    try:
        # Delete all rows
        result = supabase.table(TABLE_NAME).delete().neq("load_id", "").execute()
        print(f"Cleared existing data from {TABLE_NAME} table")
    except Exception as e:
        print(f"Warning: Could not clear table (table may not exist): {e}")


def check_table_exists(supabase: Client) -> bool:
    """Check if the loads table exists by attempting to select from it."""
    try:
        # Try to select a single row to check if table exists
        result = supabase.table(TABLE_NAME).select("*").limit(1).execute()
        return True
    except Exception as e:
        print(f"Table {TABLE_NAME} may not exist: {e}")
        return False


def upsert_loads(supabase: Client, loads: Sequence[dict[str, object]]) -> int:
    """Insert loads data using upsert to handle conflicts."""
    try:
        # Insert data in batches to avoid API limits
        batch_size = 100
        total_inserted = 0

        for i in range(0, len(loads), batch_size):
            batch = loads[i : i + batch_size]
            result = supabase.table(TABLE_NAME).upsert(batch).execute()
            total_inserted += len(batch)
            print(f"Processed batch {i // batch_size + 1}: {len(batch)} records")

        return total_inserted
    except Exception as e:
        raise RuntimeError(f"Failed to insert loads: {e}")


def main() -> None:
    loads = load_seed_data(DATA_PATH)

    # Create Supabase client with minimal options
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception as e:
        print(f"Failed to create Supabase client: {e}")
        print(
            "This may be due to a version compatibility issue with the supabase library."
        )
        print("Try updating the supabase library: pip install --upgrade supabase")
        return

    # Check if table exists
    table_exists = check_table_exists(supabase)

    if table_exists:
        print(f"Table {TABLE_NAME} exists, clearing existing data...")
        clear_table(supabase)
        action = "Reseeded"
    else:
        print(
            f"Table {TABLE_NAME} may not exist. Attempting to create via first insert..."
        )
        action = "Created table and seeded"

    # Insert the loads data
    inserted_count = upsert_loads(supabase, loads)

    print(f"{action} {TABLE_NAME} with {inserted_count} rows")


if __name__ == "__main__":
    main()
