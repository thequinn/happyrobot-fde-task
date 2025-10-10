"""Seed or reseed Supabase tables for loads and call logs using the Supabase API.

This script complements `seed_supabase.py` by using the Supabase client library
instead of direct Postgres access. It can reset and seed:

1. The freight `loads` table from `backend/data/loads.json`.
2. The call metrics table (call logs) from `backend/data/call_logs.json` when present.

For each target table the script:
  • Ensures the table is reachable.
  • Clears existing rows (optional for first-time runs).
  • Inserts the JSON payload in manageable batches.
"""

from __future__ import annotations

import os, json
from pathlib import Path
from typing import Sequence
import sys

from dotenv import load_dotenv
from supabase import create_client, Client

# Environment setup – resolve project paths and look for an optional .env file.
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.compat import ensure_httpx_proxy_support

LOADS_DATA_PATH = BASE_DIR / "data" / "loads.json"
CALL_LOGS_DATA_PATH = BASE_DIR / "data" / "call_logs.json"
ENV_PATH = BASE_DIR.parent / ".env"

# Environment setup – load .env automatically so local runs inherit Supabase creds.
if load_dotenv(ENV_PATH):
    print("Loaded environment variables from .env file")

# Environment setup – read required Supabase credentials and fail fast on missing keys.
try:
    SUPABASE_URL = os.environ["SUPABASE_URL"]
    SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
except KeyError as exc:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in your environment or .env file"
    ) from exc

LOADS_TABLE_NAME = os.getenv("SUPABASE_LOADS_TABLE", "loads")
CALL_LOGS_TABLE_NAME = os.getenv("SUPABASE_CALL_METRICS_TABLE", "call_metrics")


def load_seed_data(path: Path) -> list[dict[str, object]]:
    """Load seed data – parse JSON and ensure default booking state."""
    with path.open("r", encoding="utf-8") as json_file:
        payload = json.load(json_file)
    if not isinstance(payload, list):
        raise ValueError("Seed data must be a list of load objects")
    normalized: list[dict[str, object]] = []
    for item in payload:
        record = dict(item)
        record.setdefault("load_booked", "Y")
        normalized.append(record)
    return normalized


def load_call_log_seed_data(path: Path) -> list[dict[str, object]]:
    """Load call log seed data – parse JSON array of call log entries."""
    with path.open("r", encoding="utf-8") as json_file:
        payload = json.load(json_file)
    if not isinstance(payload, list):
        raise ValueError("Call log seed data must be a list of objects")
    normalized: list[dict[str, object]] = []
    for item in payload:
        record = dict(item)
        normalized.append(record)
    return normalized


def clear_table(
    supabase: Client,
    table_name: str,
    primary_key: str,
    *,
    sentinel: str | None = None,
) -> None:
    """Clear all data from a Supabase table using its primary key."""
    try:
        # Reset table (if present) – delete all rows to reseed cleanly.
        if sentinel is None:
            sentinel = ""
        supabase.table(table_name).delete().neq(primary_key, sentinel).execute()
        print(f"Cleared existing data from {table_name} table")
    except Exception as e:
        print(f"Warning: Could not clear table {table_name} (table may not exist): {e}")


def check_table_exists(supabase: Client, table_name: str) -> bool:
    """Check if a Supabase table exists by attempting to select from it."""
    try:
        # Check table presence – issue a small select to verify the table exists.
        supabase.table(table_name).select("*").limit(1).execute()
        return True
    except Exception as e:
        print(f"Table {table_name} may not exist: {e}")
        return False


def write_batches(
    supabase: Client,
    table_name: str,
    records: Sequence[dict[str, object]],
    *,
    batch_size: int = 100,
    method: str = "upsert",
) -> int:
    """Persist records to Supabase in manageable batches."""
    if not records:
        return 0

    if method not in {"upsert", "insert"}:
        raise ValueError("method must be either 'upsert' or 'insert'")

    try:
        # Upsert batches – insert in chunks of 100 to respect API limits.
        total_inserted = 0

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            table = supabase.table(table_name)
            if method == "insert":
                response = table.insert(batch).execute()
            else:
                response = table.upsert(batch).execute()
            if getattr(response, "error", None):
                raise RuntimeError(response.error)
            total_inserted += len(batch)
            print(f"Processed batch {i // batch_size + 1}: {len(batch)} records")

        return total_inserted
    except Exception as e:
        raise RuntimeError(f"Failed to persist records for {table_name}: {e}")


def seed_loads_table(supabase: Client) -> None:
    """Seed the loads table from loads.json."""
    if not LOADS_DATA_PATH.exists():
        print("No loads.json file found; skipping loads seeding.")
        return

    loads = load_seed_data(LOADS_DATA_PATH)
    table_exists = check_table_exists(supabase, LOADS_TABLE_NAME)

    if table_exists:
        print(f"\nTable {LOADS_TABLE_NAME} exists, clearing existing data...")
        clear_table(supabase, LOADS_TABLE_NAME, "load_id", sentinel="")
        action = "Reseeded"
    else:
        print(
            f"\nTable {LOADS_TABLE_NAME} may not exist. "
            "Attempting to create via first insert..."
        )
        action = "Created table and seeded"

    inserted_count = write_batches(
        supabase, LOADS_TABLE_NAME, loads, batch_size=100, method="upsert"
    )
    print(f"{action} {LOADS_TABLE_NAME} with {inserted_count} rows")


def seed_call_logs_table(supabase: Client) -> None:
    """Seed the call metrics table from call_logs.json when available."""
    if not CALL_LOGS_DATA_PATH.exists():
        print("No call_logs.json file found; skipping call log seeding.")
        return

    call_logs = load_call_log_seed_data(CALL_LOGS_DATA_PATH)
    table_exists = check_table_exists(supabase, CALL_LOGS_TABLE_NAME)

    if table_exists:
        print(f"\nTable {CALL_LOGS_TABLE_NAME} exists, clearing existing data...")
        clear_table(
            supabase,
            CALL_LOGS_TABLE_NAME,
            "call_id",
            sentinel="00000000-0000-0000-0000-000000000000",
        )
        action = "Reseeded"
    else:
        print(
            f"\nTable {CALL_LOGS_TABLE_NAME} may not exist. Attempting to create via first insert..."
        )
        action = "Created table and seeded"

    inserted_count = write_batches(
        supabase, CALL_LOGS_TABLE_NAME, call_logs, batch_size=100, method="insert"
    )
    print(f"{action} {CALL_LOGS_TABLE_NAME} with {inserted_count} rows")


def main() -> None:
    ensure_httpx_proxy_support()
    # Connect to Supabase – initialize client with service-role credentials.
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception as e:
        print(f"Failed to create Supabase client: {e}")
        print(
            "This may be due to a version compatibility issue with the supabase library."
        )
        print("Try updating the supabase library: pip install --upgrade supabase")
        return

    # Load seed data – read loads.json and call_logs.json (if present).
    seed_loads_table(supabase)
    seed_call_logs_table(supabase)


if __name__ == "__main__":
    main()
