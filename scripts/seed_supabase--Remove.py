"""Seed or reseed the Supabase loads table from loads.json.

Steps:
1. Ensure the target table exists (create if missing).
2. Insert or upsert rows from the JSON seed file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv
import psycopg

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / "loads.json"
ENV_PATH = BASE_DIR / ".env"

if load_dotenv(ENV_PATH):
    print("Loaded environment variables from .env file")

try:
    SUPABASE_DB_URL = os.environ["SUPABASE_DB_URL"]
except KeyError as exc:
    raise RuntimeError(
        "SUPABASE_DB_URL must be set in your environment or .env file"
    ) from exc
TABLE_NAME = os.getenv("SUPABASE_LOADS_TABLE", "loads")

# Create the table if it doesn’t exist.
CREATE_TABLE_SQL = f"""
create table if not exists public.{TABLE_NAME} (
  load_id text primary key,
  load_booked text default 'Y',
  counter_offer numeric,
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

CLEAR_TABLE_SQL = f"delete from public.{TABLE_NAME};"
ALTER_COLUMN_SQL = [
    f"alter table public.{TABLE_NAME} add column if not exists load_booked text default 'Y';",
    f"alter table public.{TABLE_NAME} add column if not exists counter_offer numeric;",
]

# Insert this row if it doesn’t exist. If it does exist, update it.
UPSERT_SQL = f"""
insert into public.{TABLE_NAME} (
  load_id,
  load_booked,
  counter_offer,
  origin,
  destination,
  pickup_datetime,
  delivery_datetime,
  equipment_type,
  loadboard_rate,
  notes,
  weight,
  commodity_type,
  num_of_pieces,
  miles,
  dimensions
) values (
  %(load_id)s,
  %(load_booked)s,
  %(counter_offer)s,
  %(origin)s,
  %(destination)s,
  %(pickup_datetime)s,
  %(delivery_datetime)s,
  %(equipment_type)s,
  %(loadboard_rate)s,
  %(notes)s,
  %(weight)s,
  %(commodity_type)s,
  %(num_of_pieces)s,
  %(miles)s,
  %(dimensions)s
) 
on conflict (load_id) do update set
  origin = excluded.origin,
  load_booked = excluded.load_booked,
  counter_offer = excluded.counter_offer,
  destination = excluded.destination,
  pickup_datetime = excluded.pickup_datetime,
  delivery_datetime = excluded.delivery_datetime,
  equipment_type = excluded.equipment_type,
  loadboard_rate = excluded.loadboard_rate,
  notes = excluded.notes,
  weight = excluded.weight,
  commodity_type = excluded.commodity_type,
  num_of_pieces = excluded.num_of_pieces,
  miles = excluded.miles,
  dimensions = excluded.dimensions
;
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
        record.setdefault("counter_offer", None)
        normalized.append(record)
    return normalized


def ensure_table_exists(connection: psycopg.Connection) -> bool:
    """Create the loads table if it does not already exist.

    Returns True if the table already existed, False if it was newly created.
    """

    with connection.cursor() as cur:
        cur.execute("select to_regclass(%s)", (f"public.{TABLE_NAME}",))
        exists = cur.fetchone()[0] is not None
        if not exists:
            cur.execute(CREATE_TABLE_SQL)
        else:
            for statement in ALTER_COLUMN_SQL:
                cur.execute(statement)
    connection.commit()
    return exists


def clear_table(connection: psycopg.Connection) -> None:
    with connection.cursor() as cur:
        cur.execute(CLEAR_TABLE_SQL)
    connection.commit()


def upsert_loads(
    connection: psycopg.Connection, loads: Sequence[dict[str, object]]
) -> int:
    with connection.cursor() as cur:
        cur.executemany(UPSERT_SQL, loads)
    connection.commit()
    return len(loads)


def main() -> None:
    loads = load_seed_data(DATA_PATH)

    with psycopg.connect(SUPABASE_DB_URL) as conn:
        existed = ensure_table_exists(conn)
        if existed:
            clear_table(conn)
        upsert_loads(conn, loads)

    action = "Reseeded" if existed else "Created table and seeded"
    print(f"{action} {TABLE_NAME} with {len(loads)} rows")


if __name__ == "__main__":
    main()
