# HappyRobot Platform

The HappyRobot Platform consists of:

A FastAPI backend service powering HappyRobot.ai’s agentic workflows. It currently exposes read endpoints for querying Supabase-hosted loads and tracking inbound call activity. Designed for deployment on Google Cloud Run with Supabase as the datastore.

A Streamlit-based frontend for visualizing use case metrics.

Local setup instructions for running both components in development.

## Project Overview

The repository is now split into two deployable units:

- `backend/` – FastAPI service that powers inbound load lookups, call metrics aggregation, and call-log CRUD.
- `frontend/` – Streamlit dashboard that visualizes call metrics by calling the backend's `/metrics/summary` endpoint.

```
.
├── backend
│   ├── app
│   │   ├── config.py, db.py, main.py, models.py, routes/, services/, ...
│   ├── data
│   │   ├── loads.json
│   │   └── call_logs.json
│   ├── scripts
│   │   └── seed_supabase_api.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend
│   ├── streamlit_app.py
│   └── requirements.txt
└── README.md
```

The shared `.env` file remains at the repository root so both the backend scripts and the Streamlit dashboard can load credentials without duplication.

## Features

- Supabase-backed persistence for freight loads stored in the `loads` table.
- Parameterized filtering by `origin`, `destination`, and `equipment_type` via SQL `ILIKE` queries at `/get_loads` (GET).
- Call log CRUD endpoints (`/call_logs`) to capture inbound carrier interactions in real time.
- Aggregated call-metrics endpoint at `/metrics/summary` (GET) to support operational dashboards.
- API key authentication enforced through the `Authorization: Bearer <api_key>` header.
- FastAPI auto-generated docs available at `/docs` and `/redoc`.
- Container-ready setup for Google Cloud Run with HTTPS termination handled by the platform.

## API Endpoints

| Method | Path                   | Description                                                                                                                  |
| ------ | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/get_loads`           | Returns loads filtered by `origin`, `destination`, and `equipment_type`. Only loads with `load_booked = 'Y'` are returned.   |
| GET    | `/metrics/summary`     | Returns aggregate statistics across inbound carrier calls (total count, sentiment distribution, and call outcome breakdown). |
| GET    | `/call_logs`           | Lists call log records with pagination support.                                                                              |
| POST   | `/call_logs`           | Creates a new call log entry (load, sentiment, outcome).                                                                     |
| GET    | `/call_logs/{call_id}` | Fetches a specific call log by identifier.                                                                                   |
| PATCH  | `/call_logs/{call_id}` | Partially updates an existing call log.                                                                                      |
| DELETE | `/call_logs/{call_id}` | Deletes a call log.                                                                                                          |
| GET    | `/health`              | Simple health check used for uptime monitoring.                                                                              |

## Requirements

- Python 3.11+
- A Supabase project with a `loads` table matching the schema in [`backend/data/loads.json`](backend/data/loads.json).
- Supabase service role key for privileged read operations.
- API key value you will share with trusted brokerages.

## Configuration

The application reads configuration from environment variables (optionally via a local `.env` file):

| Variable                      | Description                                                                                                 |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `SUPABASE_URL`                | Supabase project URL.                                                                                       |
| `SUPABASE_SERVICE_ROLE_KEY`   | Supabase service role key used to query the database.                                                       |
| `SUPABASE_LOADS_TABLE`        | (Optional) Table name; defaults to `loads`.                                                                 |
| `SUPABASE_CALL_METRICS_TABLE` | (Optional) Table name holding call logs; defaults to `call_metrics`.                                        |
| `LOAD_API_KEY`                | API key required in the `Authorization` header to access the server's endpoints. Set your own secret value. |
| `SUPABASE_DB_URL`             | Postgres connection string (service role credentials).                                                      |

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

### Backend (FastAPI)

1. Install dependencies and run the API:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
2. Send authenticated requests (GET loads):
   ```bash
   curl -H "Authorization: Bearer $LOAD_API_KEY" \
        "http://127.0.0.1:8000/get_loads?origin=Chicago"
   ```
3. Send authenticated requests (POST call logs):
   ```bash
   curl -X POST "http://127.0.0.1:8000/call_logs" \
     -H "Authorization: Bearer $LOAD_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
           "load_id": "L005",
           "call_started_at": "2025-09-28T14:30:00Z",
           "sentiment": "positive",
           "outcome": "accepted"
         }'
   ```
4. Send authenticated requests (GET call metrics):
   ```bash
   curl -H "Authorization: Bearer $LOAD_API_KEY" \
        "http://127.0.0.1:8000/metrics/summary"
   ```
5. Health check endpoint: `http://localhost:8000/health`

. Visit the interactive docs at `http://127.0.0.1:8000/docs` or `http://127.0.0.1:8000/redoc`.

## Setting up ngrok

Agent nodes on HappyRobot.ai are cloud-based—they live on the public internet. Your localhost, by contrast, is a private environment running on your machine (e.g., `http://localhost:8000`), and it’s not publicly routable.

So when a webhook node tries to hit `http://localhost:8000/negotiate`, it fails because:

1. Localhost is not exposed to the internet.
2. HappyRobot’s cloud agents need a public URL to reach your server.

### Why ngrok solves this

Ngrok creates a secure tunnel from the public internet to your local machine. It gives you a temporary public URL like `https://abc123.ngrok.io`, which forwards requests to your local server.

So now:

- HappyRobot’s webhook node can call `https://abc123.ngrok.io/negotiate`.
- Ngrok forwards that to `http://localhost:8000/negotiate` on your machine.
- Your local FastAPI server responds, and the agent chain continues.

---

### Instructions to set up ngrok

1. **Install ngrok**

   ```bash
   brew install ngrok
   ```

2. **Connect ngrok to your account**

   Run the following command to add your auth token to the default `ngrok.yml`:

   ```bash
   ngrok config add-authtoken <YOUR_AUTH_TOKEN>
   ```

   Replace `<YOUR_AUTH_TOKEN>` with the value from your ngrok dashboard.

   You can find the `ngrok.yml` location with:

   ```bash
   ngrok config check
   ```

3. **Start your local server**

   Launch your FastAPI server (default setup):

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Start ngrok and expose your service**

   ```bash
   ngrok http 8000
   ```

   Replace `8000` with the port number your FastAPI server is running on.

5. **Use the public URL provided**

   Ngrok will display HTTP and HTTPS URLs that forward to your local machine, for example:

   ```
   Forwarding https://swaggering-danuta-unpaved.ngrok-free.dev -> http://localhost:8000
   ```

6. **(Optional) Inspect traffic**

   Visit `http://127.0.0.1:4040` to inspect the HTTP traffic passing through ngrok.

**Example URL substitution:**

- Local: `https://localhost:8000/get_loads?origin=Chicago&destination=Dallas&equipment_type=Dry%20Van`
- Public via ngrok: `https://swaggering-danuta-unpaved.ngrok-free.dev/get_loads?origin=Chicago&destination=Dallas&equipment_type=Dry%20Van`

### Frontend (Streamlit)

1. In a new shell:
   ```bash
   cd frontend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   streamlit run streamlit_app.py
   ```
2. Ensure `API_BASE_URL` points at the running backend and `LOAD_API_KEY` matches your FastAPI configuration (set via shell exports or `.env`).

### Supabase Table Setup

### Loads Table

Create the `loads` table in Supabase with columns matching the sample payload. You can do it by running the SQL in the Supabase dashboard (SQL Editor), via `psql`, or using the Supabase CLI. Using `if not exists` keeps the statement idempotent.

SQL example:

```sql
create table if not exists public.loads (
  load_id text primary key,
  load_booked text default 'N',
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

Seed data using the Supabase dashboard or CLI with the entries in [`backend/data/loads.json`](backend/data/loads.json), or use the Supabase API-based seeder to populate both loads and call logs from JSON:

```bash
python backend/scripts/seed_supabase_api.py
```

This script reads [`backend/data/loads.json`](backend/data/loads.json) and writes them to Supabase using the service-role API key defined in `.env`.

### Call Metrics Table

Create a second table to track inbound carrier call activity. You can do it by running the SQL in the Supabase dashboard (SQL Editor), via `psql`, or using the Supabase CLI. Using `if not exists` keeps the statement idempotent.

The backend expects (at minimum) the columns shown below; add extra fields as needed for your workflow (e.g., carrier contact info, pricing notes).

```sql
create table if not exists public.call_metrics (
  call_id uuid primary key default gen_random_uuid(),
  load_id text,
  call_started_at timestamptz not null,
  sentiment text not null,
  outcome text not null
);
```

Populate the table with representative historical calls to power the dashboard:

```sql
insert into public.call_metrics
  (load_id, call_started_at, sentiment, outcome)
values
  ('L001', now() - interval '2 hours', 'positive', 'accepted'),
  ('L002', now() - interval '6 hours', 'neutral', 'rejected'),
  ('L003', now() - interval '1 day', 'negative', 'canceled');
```

Once populated, the `/metrics/summary` endpoint will aggregate the totals for the dashboard.

You can also edit [`backend/data/call_logs.json`](backend/data/call_logs.json) and run `python backend/scripts/seed_supabase_api.py` to reseed the `call_metrics` table via the Supabase API.

With the CRUD API in place you can now push call activity directly from your HappyRobot agent:

```bash
curl -X POST "https://<host>/call_logs" \
  -H "Authorization: Bearer $LOAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "load_id": "L005",
        "call_started_at": "2025-09-28T14:30:00Z",
        "sentiment": "positive",
        "outcome": "accepted"
      }'
```

Use `GET /call_logs?limit=50&offset=0` to paginate through historical calls, `PATCH /call_logs/{call_id}` to adjust metadata, and `DELETE /call_logs/{call_id}` when you need to purge records.

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

- `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` – run locally with autoreload (from the `backend/` directory).
- `docker build -t load-search-api backend` – build the container from the backend folder.
- `gcloud run services describe load-search-api --region REGION` – inspect deployed service.
