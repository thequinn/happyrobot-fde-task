"""Seed or reseed the Supabase loads table from loads.json using HTTP requests.

This approach uses direct HTTP requests to the Supabase REST API to avoid
dependency conflicts with the Python client library.

Steps:
1. Clear existing data from the loads table.
2. Insert rows from the JSON seed file using REST API.
"""

from __future__ import annotations

import json
import os
import requests
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

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

# Supabase REST API endpoints
REST_URL = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}"
HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def load_seed_data(path: Path) -> list[dict[str, object]]:
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


def clear_table() -> None:
    """Clear all data from the loads table."""
    try:
        # Delete all rows (using a condition that matches all rows)
        response = requests.delete(
            f"{REST_URL}?load_id=neq.",  # matches all rows (not equal to empty string)
            headers=HEADERS,
        )
        response.raise_for_status()
        print(f"Cleared existing data from {TABLE_NAME} table")
    except requests.RequestException as e:
        print(f"Warning: Could not clear table: {e}")


def check_table_exists() -> bool:
    """Check if the loads table exists by attempting to query it."""
    try:
        # Try to select from the table with a limit
        response = requests.get(f"{REST_URL}?limit=1", headers=HEADERS)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Table {TABLE_NAME} may not exist or is inaccessible: {e}")
        return False


def insert_loads(loads: Sequence[dict[str, object]]) -> int:
    """Insert loads data using the REST API."""
    try:
        # Insert data in batches to avoid request size limits
        batch_size = 100
        total_inserted = 0

        for i in range(0, len(loads), batch_size):
            batch = loads[i : i + batch_size]

            # Use upsert to handle conflicts
            headers_with_upsert = {
                **HEADERS,
                "Prefer": "resolution=merge-duplicates,return=representation",
            }

            response = requests.post(REST_URL, headers=headers_with_upsert, json=batch)
            response.raise_for_status()

            total_inserted += len(batch)
            print(f"Processed batch {i // batch_size + 1}: {len(batch)} records")

        return total_inserted
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to insert loads: {e}")


def main() -> None:
    loads = load_seed_data(DATA_PATH)

    # Check if table exists
    table_exists = check_table_exists()

    if not table_exists:
        print(
            f"Cannot access table {TABLE_NAME}. Please ensure the table exists and your service role key has the correct permissions."
        )
        return

    print(f"Table {TABLE_NAME} exists, clearing existing data...")
    clear_table()

    # Insert the loads data
    inserted_count = insert_loads(loads)

    print(f"Reseeded {TABLE_NAME} with {inserted_count} rows")


if __name__ == "__main__":
    main()
