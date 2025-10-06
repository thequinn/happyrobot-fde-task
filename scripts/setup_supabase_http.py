"""Create the Supabase loads table and seed it from loads.json using HTTP requests.

This script will:
1. Create the loads table if it doesn't exist using raw SQL via the Supabase HTTP API
2. Clear existing data from the loads table
3. Insert rows from the JSON seed file using REST API
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

# Supabase API endpoints
REST_URL = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}"
SQL_URL = f"{SUPABASE_URL}/rest/v1/rpc"

HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# SQL to create the table
CREATE_TABLE_SQL = f"""
create table if not exists public.{TABLE_NAME} (
  load_id text primary key,
  load_booked text default 'Y',
  origin text not null,
  destination text not null,
  pickup_datetime timestamptz,
  delivery_datetime timestamptz,
  equipment_type text not null,
  loadboard_rate numeric,
  notes text,
  weight integer,
  commodity_type text,
  num_of_pieces integer,
  miles integer,
  dimensions text
);
"""

# Additional columns (in case table exists but is missing new columns)
ALTER_COLUMNS_SQL = f"""
alter table public.{TABLE_NAME} add column if not exists load_booked text default 'Y';
"""


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


def execute_sql(sql: str) -> bool:
    """Execute raw SQL using Supabase's SQL endpoint."""
    try:
        # First, try using a direct SQL execution approach
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/exec_sql", headers=HEADERS, json={"sql": sql}
        )

        # If that doesn't work, try the alternative approach using query parameter
        if response.status_code == 404:
            # Try using query parameter instead
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/",
                headers={
                    **HEADERS,
                    "Content-Type": "application/vnd.pgrst.object+json",
                },
                json={"query": sql},
            )

        # If still doesn't work, we'll need to create the table manually via the dashboard
        if response.status_code >= 400:
            print(
                f"SQL execution failed with status {response.status_code}: {response.text}"
            )
            return False

        response.raise_for_status()
        print("SQL executed successfully")
        return True

    except requests.RequestException as e:
        print(f"Failed to execute SQL: {e}")
        return False


def create_table() -> bool:
    """Create the loads table if it doesn't exist."""
    print(f"Creating table {TABLE_NAME}...")
    success = execute_sql(CREATE_TABLE_SQL)

    if success:
        # Also run the ALTER statements to add any missing columns
        execute_sql(ALTER_COLUMNS_SQL)

    return success


def clear_table() -> None:
    """Clear all data from the loads table."""
    try:
        # Delete all rows (using a condition that matches all rows)
        response = requests.delete(
            f"{REST_URL}?load_id=neq.",  # matches all rows (not equal to empty string)
            headers=HEADERS,
        )

        if response.status_code == 200:
            print(f"Cleared existing data from {TABLE_NAME} table")
        elif response.status_code == 404:
            print(f"Table {TABLE_NAME} is empty or does not exist")
        else:
            response.raise_for_status()

    except requests.RequestException as e:
        print(f"Warning: Could not clear table: {e}")


def check_table_exists() -> bool:
    """Check if the loads table exists by attempting to query it."""
    try:
        # Try to select from the table with a limit
        response = requests.get(f"{REST_URL}?limit=1", headers=HEADERS)

        if response.status_code == 200:
            return True
        elif response.status_code == 404:
            return False
        else:
            response.raise_for_status()
            return True  # If we get here, the request was successful

    except requests.RequestException as e:
        print(f"Error checking table existence: {e}")
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

            if response.status_code in [200, 201]:
                total_inserted += len(batch)
                print(f"Processed batch {i // batch_size + 1}: {len(batch)} records")
            else:
                print(
                    f"Warning: Batch {i // batch_size + 1} failed with status {response.status_code}: {response.text}"
                )

        return total_inserted
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to insert loads: {e}")


def main() -> None:
    loads = load_seed_data(DATA_PATH)
    print(f"Loaded {len(loads)} records from {DATA_PATH}")

    # Check if table exists
    table_exists = check_table_exists()

    if not table_exists:
        print(f"Table {TABLE_NAME} does not exist. Creating it...")

        # For now, let's create the table manually via INSERT attempt
        # This is a workaround since we don't have direct SQL execution access
        print(
            "Since we cannot execute raw SQL via the API, we'll create the table by attempting an insert."
        )
        print(
            "If this fails, you'll need to create the table manually in the Supabase dashboard."
        )
        print("Use this SQL:")
        print(CREATE_TABLE_SQL)

        # Try to insert one record to trigger table creation (this will likely fail)
        try:
            response = requests.post(REST_URL, headers=HEADERS, json=[loads[0]])
            if response.status_code == 404:
                print("\\nPlease create the table manually in your Supabase dashboard:")
                print("1. Go to your Supabase project dashboard")
                print("2. Navigate to the SQL Editor")
                print("3. Run the following SQL:")
                print(CREATE_TABLE_SQL)
                print("4. Then run this script again")
                return
        except Exception:
            pass
    else:
        print(f"Table {TABLE_NAME} exists")

    # Clear existing data
    print("Clearing existing data...")
    clear_table()

    # Insert the loads data
    print("Inserting new data...")
    inserted_count = insert_loads(loads)

    if inserted_count > 0:
        print(f"Successfully seeded {TABLE_NAME} with {inserted_count} rows")
    else:
        print(
            "No records were inserted. Please check your Supabase configuration and table permissions."
        )


if __name__ == "__main__":
    main()
