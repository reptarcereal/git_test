# Starlink Overage Dashboard

A web dashboard that reports **data-cap overages across 200+ Starlink service
lines** using the Starlink **Enterprise / Account Management API v2**.

A background job polls usage for every service line on a schedule and stores
snapshots in a local database; the dashboard reads that database, so the UI is
fast and resilient to API rate limits even with hundreds of lines.

## Features

- **Fleet summary** — total lines, # over cap, # approaching cap, total overage
  GB, and estimated overage cost.
- **Per-line table** — utilization bar, used/included GB, overage, and estimated
  cost; filterable by status (`over` / `warning` / `ok`) and searchable by name
  or service-line number, sorted worst-offenders-first.
- **Scheduled polling** with OAuth2 client-credentials auth, pagination, and
  rate-limit (HTTP 429) backoff.
- **Mock mode** — runs end-to-end with 220 synthetic lines when no credentials
  are present, so you can demo it immediately.

## Architecture

```
Starlink API v2  ──poll (hourly)──▶  FastAPI poller  ──▶  SQLite/Postgres
                                                              │
                                          React (Vite) UI ◀─ REST /api/*
```

- `backend/app/starlink_client.py` — OAuth2 + paginated usage fetch. The JSON→
  model mapping (`_parse_service_line`) is isolated and **clearly marked**;
  adjust it to your account's exact payload shape.
- `backend/app/overage.py` — the single source of truth for overage math.
- `backend/app/poller.py` — scheduled fetch → compute → persist.
- `backend/app/main.py` — REST API + serves the built frontend.
- `frontend/` — React + TypeScript dashboard.

## Quick start

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp ../.env.example .env   # then edit .env (or export env vars)
uvicorn app.main:app --reload --port 8000
```

With no credentials set, the backend starts in **mock mode** (banner shown in
the UI). To use live data, set in `.env`:

```
STARLINK_CLIENT_ID=...
STARLINK_CLIENT_SECRET=...
STARLINK_ACCOUNT_NUMBER=ACC-...
```

> The `.env` is loaded from the directory you run `uvicorn` in. Running from
> `backend/`, copy `.env.example` to `backend/.env`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev          # dev server on :5173, proxies /api to :8000
# or, for production:
npm run build        # outputs frontend/dist, which the backend serves at /
```

In production you can run **just the backend** after `npm run build` — FastAPI
serves the built UI at `/` and the API at `/api/*`.

## API

| Method | Path                  | Description                                   |
|--------|-----------------------|-----------------------------------------------|
| GET    | `/api/health`         | Liveness check                                |
| GET    | `/api/summary`        | Fleet totals + overage cost + mock flag       |
| GET    | `/api/service-lines`  | Latest usage per line (`?status=`, `?search=`)|
| GET    | `/api/overages`       | Only `warning`/`over` lines                   |
| POST   | `/api/refresh`        | Trigger an immediate poll (synchronous)       |
| GET    | `/api/poll-runs`      | Recent poll runs (observability)              |

## Configuration

All settings come from environment variables / `.env` — see
[`.env.example`](.env.example). Key ones:

| Variable                | Default | Purpose                                       |
|-------------------------|---------|-----------------------------------------------|
| `POLL_INTERVAL_SECONDS` | `3600`  | How often to refresh usage                    |
| `POLL_PAGE_SIZE`        | `100`   | Service lines per API page / usage batch      |
| `WARNING_THRESHOLD_PCT` | `80`    | % of allotment that flags a line `warning`    |
| `OVERAGE_COST_PER_GB`   | `1.00`  | $/GB used for estimated overage cost          |
| `DATABASE_URL`          | sqlite  | Set a Postgres URL for production             |

## Overage logic

Only **priority (included-allotment) data** counts against the cap.

- `overage_gb = max(0, priority_used − included)`
- `used_pct  = priority_used / included × 100`
- status: `over` if any overage, else `warning` at/above the threshold, else `ok`
- a line with no/zero allotment is treated as uncapped and never `over`

## Adapting to your real API payloads

Starlink response shapes vary by account and API revision. If live data looks
empty or wrong, adjust **only** `_parse_service_line` / `_parse_usage` and the
endpoint paths in `starlink_client.py` to match the JSON your account returns —
the rest of the pipeline is shape-agnostic.

## Tests

```bash
cd backend && source .venv/bin/activate && pytest
```
