"""Seed the Supabase `loads` table using data from loads.json."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / "loads.json"

load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
TABLE_NAME = os.getenv("SUPABASE_LOADS_TABLE", "loads")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

with DATA_PATH.open("r", encoding="utf-8") as json_file:
    loads = json.load(json_file)

resp = supabase.table(TABLE_NAME).upsert(loads).execute()

error = getattr(resp, "error", None)
if error:
    raise RuntimeError(error)

print(f"Inserted/updated {len(loads)} rows into '{TABLE_NAME}'")
