# SEC Management Change Tracker

Tracks director/officer changes disclosed by SEC-listed companies (Form 8-K,
Item 5.02) and makes them searchable through a website backed by a database
that's refreshed from SEC EDGAR.

- **Backend**: Python (FastAPI + SQLAlchemy), ingests data from EDGAR's
  `company_tickers.json` and per-company `submissions` APIs.
- **Frontend**: Next.js, queries the backend API and renders a filterable table.
- **Database**: SQLite by default (zero setup). Point `DATABASE_URL` at
  Postgres when you're ready to host this (see below) — the code doesn't change.

All requests to SEC EDGAR are sent with a `User-Agent` set from
`SEC_USER_AGENT` (`backend/.env`), per SEC's fair-access requirements.

## Project layout

```
backend/    FastAPI app + EDGAR ingestion script
frontend/   Next.js website
```

## Running locally

**Backend**
```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # edit SEC_USER_AGENT if needed
.venv\Scripts\python -m uvicorn app.main:app --reload
```
API is now at http://localhost:8000 (docs at `/docs`).

**Ingest data** (populates the database from EDGAR — run this before/while using the site):
```bash
cd backend
.venv\Scripts\python -m app.ingest --limit 50   # small test batch
.venv\Scripts\python -m app.ingest              # full run, all ~10,000+ filers (takes a while; respects EDGAR rate limits)
```
Re-running the ingest is safe — it only adds new events (deduped by SEC accession number) and refreshes company info.

**Frontend**
```bash
cd frontend
npm install
copy .env.local.example .env.local
npm run dev
```
Site is now at http://localhost:3000.

## Current scope (v1)

- Signal: Form 8-K filings with Item 5.02 (departure/election of directors or officers).
- Filters: company name/ticker search, filing date range.
- Each row links straight to the filing on sec.gov.

Planned next: SIC/industry filters, XBRL financial data, full-text search,
insider transaction (Forms 3/4/5) tracking, and scheduled/incremental
ingestion instead of full manual re-runs.

## Deploying (Render + Vercel)

The backend, database, and scheduled jobs deploy to **Render** via
[`render.yaml`](render.yaml); the frontend deploys to **Vercel**.

**1. Push this repo to GitHub** (if you haven't already).

**2. Backend + database + cron jobs, on Render:**
1. In the Render dashboard: **New > Blueprint**, connect this GitHub repo. Render
   reads `render.yaml` and provisions a free Postgres database, a web service
   for the API, and three cron jobs (ingest, name extraction, market cap).
2. Cron jobs are a paid Render feature (the blueprint sets them to the
   cheapest `starter` plan). If you'd rather not pay for that yet, delete the
   three `type: cron` blocks from `render.yaml` before deploying, and instead
   run those same commands manually from the web service's **Shell** tab in
   the Render dashboard whenever you want fresh data.
3. In the web service's **Environment** tab, set the secrets `render.yaml`
   leaves blank: `SEC_USER_AGENT`, `ANTHROPIC_API_KEY`, and `CORS_ORIGINS`
   (set this to your Vercel URL once you have it, e.g.
   `https://sec-mgmt-tracker.vercel.app`).
4. **Migrate your existing local data** (skip this if you're fine starting
   fresh and just re-running the ingest scripts on Render instead): copy the
   Postgres "External Connection String" from Render's database page, then
   run locally:
   ```bash
   cd backend
   .venv\Scripts\python -m app.migrate_sqlite_to_postgres "postgresql://...external-connection-string..."
   ```

**3. Frontend, on Vercel:**
1. **Add New > Project**, connect the same GitHub repo.
2. Set **Root Directory** to `frontend` (this repo has the frontend in a
   subfolder, not the repo root).
3. Set the environment variable `NEXT_PUBLIC_API_URL` to your Render web
   service's URL (e.g. `https://sec-mgmt-tracker-api.onrender.com`).
4. Deploy. Once you have the Vercel URL, go back and set it as
   `CORS_ORIGINS` on the Render backend (step 2.3) so the browser is allowed
   to call the API.

**Auth**: not implemented yet. When you're ready for multiple users, add an
auth layer (e.g. FastAPI + OAuth/session cookies, or a hosted provider like
Clerk/Auth0) in front of the API and frontend.
