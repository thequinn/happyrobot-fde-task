# Load Search API

FastAPI proof-of-concept that lets freight brokerages search Supabase-hosted load data by origin, destination, and equipment type. The service exposes a secured `/get_loads` endpoint backed by SQL filters in Supabase and is designed for deployment on Google Cloud Run.

## Features

- Supabase-backed persistence for freight loads stored in the `loads` table.
- Parameterized filtering by `origin`, `destination`, and `equipment_type` via SQL `ILIKE` queries.
- API key authentication enforced through the `Authorization: Bearer <api_key>` header.
- FastAPI auto-generated docs available at `/docs` and `/redoc`.
- Container-ready setup for Google Cloud Run with HTTPS termination handled by the platform.

## Requirements

- Python 3.11+
- A Supabase project with a `loads` table matching the schema in [`loads.json`](loads.json).
- Supabase service role key for privileged read operations.
- API key value you will share with trusted brokerages.

## Configuration

The application reads configuration from environment variables (optionally via a local `.env` file):

| Variable                    | Description                                            |
| --------------------------- | ------------------------------------------------------ |
| `SUPABASE_URL`              | Supabase project URL.                                  |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key used to query the database.  |
| `SUPABASE_LOADS_TABLE`      | (Optional) Table name; defaults to `loads`.            |
| `LOAD_API_KEY`              | API key required in the `Authorization` header.        |
| `SUPABASE_DB_URL`           | Postgres connection string (service role credentials). |

Example `.env` file for local development:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_LOADS_TABLE=loads
LOAD_API_KEY=super-secret-key
SUPABASE_DB_URL=postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres
```

## API Key Setup for all endpoints in `main.py`

1. Choose the shared secret and set `LOAD_API_KEY` in `.env` (or your secret store).
2. Load it at runtime:
   - Local: keep the `.env` file alongside the project or export `LOAD_API_KEY=...` before running Uvicorn.
   - Cloud Run: store it in Secret Manager and wire it through, or pass `--set-env-vars LOAD_API_KEY=...` during `gcloud run deploy`.
3. Deploy Cloud Run with `--allow-unauthenticated=false` to restrict callers.
4. Instruct clients to send `Authorization: Bearer <your-key>` on every `/get_loads` call; other requests return `401/403`.

## Local Development

1. Install dependencies and run the API:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
   ```
2. Send authenticated requests:
   ```bash
   curl -H "Authorization: Bearer $LOAD_API_KEY" \
        "http://127.0.0.1:8000/get_loads?origin=Chicago"
   ```
3. Health check endpoint: `http://localhost:8000/health`

4. Visit the interactive docs at `http://127.0.0.1:8000/docs` or `http://127.0.0.1:8000/redoc`.

## Supabase Table Setup

Create the `loads` table in Supabase with columns matching the sample payload. You can do it by running the SQL in the Supabase dashboard (SQL Editor), via `psql`, or using the Supabase CLI.

SQL example:

```sql
create table public.loads (
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
```

Seed data using the Supabase dashboard or CLI with the entries in [`loads.json`](loads.json), or run the helper script:

```bash
python scripts/seed_supabase.py
```

The script expects `SUPABASE_DB_URL` to point to your Supabase Postgres instance (available under Project Settings → Database). It will create the table if missing or truncate and reseed it when it already exists.

## Docker & Cloud Run Deployment

1. Build and test the container locally:
   ```bash
   docker build -t load-search-api .
   docker run --rm -p 8080:8080 \
     -e SUPABASE_URL=... \
     -e SUPABASE_SERVICE_ROLE_KEY=... \
     -e LOAD_API_KEY=... \
     load-search-api
   ```
2. Authenticate with Google Cloud and set defaults:
   ```bash
   gcloud auth login
   gcloud config set project <your-project-id>
   gcloud auth configure-docker
   ```
3. Push the image to Artifact Registry (or Container Registry):
   ```bash
   docker tag load-search-api REGION-docker.pkg.dev/<project-id>/<repo>/load-search-api:v1
   docker push REGION-docker.pkg.dev/<project-id>/<repo>/load-search-api:v1
   ```
4. Deploy to Cloud Run (fully managed):
   ```bash
   gcloud run deploy load-search-api \
     --image=REGION-docker.pkg.dev/<project-id>/<repo>/load-search-api:v1 \
     --platform=managed \
     --region=REGION \
     --allow-unauthenticated=false \
     --set-env-vars="SUPABASE_URL=..." \
     --set-env-vars="SUPABASE_SERVICE_ROLE_KEY=..." \
     --set-env-vars="LOAD_API_KEY=..." \
     --set-env-vars="SUPABASE_LOADS_TABLE=loads"
   ```
   Cloud Run provisions TLS automatically. Restrict invocation to authenticated callers or distribute your API key securely.

## Testing the Endpoint

- Use `curl`, Postman, or the FastAPI docs UI at `/docs`.
- Include `Authorization: Bearer <api_key>` in every request.
- Supply the required query parameters: `origin`, `destination`, `equipment_type`.

Example authenticated request - localhost:

```bash
curl -X GET "http://localhost:8000/get_loads?origin=Chicago&destination=Dallas&equipment_type=Dry%20Van" \
  -H "Authorization: Bearer YOUR_API_KEY_HERE"
```

Example authenticated requests - Cloud:

```bash
curl -H "Authorization: Bearer $LOAD_API_KEY" \
  "https://<cloud-run-host>/get_loads?origin=Chicago&destination=Dallas&equipment_type=Dry%20Van"
```

A successful response returns a JSON array of load records that match the filters supplied.

## Security Notes

- Rejects requests without the correct bearer token.
- Recommend storing secrets in Google Secret Manager and injecting them via environment variables.
- Use HTTPS endpoints only (Cloud Run enforces this by default).

## Useful Commands

- `uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload` – run locally with autoreload.
- `docker build -t load-search-api .` – build the container.
- `gcloud run services describe load-search-api --region REGION` – inspect deployed service.
