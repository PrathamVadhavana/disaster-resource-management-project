# Getting Started

Step-by-step guide to set up and run the Disaster Resource Management System on your local machine.

**Time required:** ~10 minutes

---

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Node.js | 20+ | `node --version` |
| npm | 9+ | `npm --version` |
| Python | 3.11+ | `python --version` |
| uv | 0.4+ | `uv --version` |
| Supabase account | Free tier | [supabase.com](https://supabase.com) |
| Docker *(optional)* | 24+ | `docker --version` |

---

## Step 1 — Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign in (or create a free account)
2. Click **New Project**, choose a name, set a **database password** (save it — you'll need it), and select a region
3. Wait ~2 minutes for provisioning to complete

### Collect your credentials

Go to **Settings → API** and copy these three values:

| Credential | Where to find it |
|------------|-----------------|
| **Project URL** | `https://xxxxx.supabase.co` |
| **Anon (public) Key** | Under "Project API keys" → `anon` `public` |
| **Service Role Key** | Under "Project API keys" → `service_role` `secret` |

Also note your **database password** from project creation.

---

## Step 2 — Run Database Setup

Open the **Supabase SQL Editor** (left sidebar → SQL Editor).

### 2a. Auth & Users (REQUIRED — do this first)

Copy the entire contents of **`database/COMPLETE_SETUP.sql`** into the SQL Editor and click **Run**.

This creates the `users` table, role-based extension tables (`victim_details`, `ngo_details`, etc.), auth triggers, RLS policies, and backfills profiles for any existing users. It is safe to run multiple times.

### 2b. Application Tables

Then run these scripts **in order**:

| # | File | Purpose |
|:-:|------|---------|
| 1 | `database/schema.sql` | Core tables: locations, disasters, resources, predictions *(skip if COMPLETE_SETUP already created users)* |
| 2 | `database/phase2_allocation_engine.sql` | Resource consumption log for forecasting |
| 3 | `database/phase3_nlp_triage.sql` | NLP training feedback table |
| 4 | `database/create_resource_requests.sql` | Victim resource requests, available_resources |
| 5 | `database/phase4_realtime_ingestion.sql` | External data sources, ingested events, weather/satellite observations, alerts |
| 6 | `database/phase5_ai_coordinator.sql` | Situation reports, NL query log, anomaly alerts, outcome tracking, evaluations |
| 7 | `database/seed_available_resources.sql` | *(Optional)* Sample resource inventory data |

**Tip:** Open each `.sql` file, copy the entire contents, paste into the SQL Editor, and click **Run**.

> **If you only want signup/login/onboarding to work**, step 2a alone is enough. The other scripts add the disaster management tables.

---

## Step 3 — Configure Environment Variables

### Backend

Create `backend/.env` (copy from `backend/.env.example`):

```env
# Required — Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-public-key
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_DB_PASSWORD=your-database-password
DATABASE_URL=postgresql+asyncpg://postgres:your-database-password@db.your-project.supabase.co:5432/postgres

# Required — App
ALLOWED_ORIGINS=http://localhost:3000
DEBUG=true

# Optional — Free-tier API keys (features work without them)
# OPENWEATHERMAP_API_KEY=         # Weather ingestion (https://openweathermap.org/api)
# FIRMS_API_KEY=                  # NASA fire data (https://firms.modaps.eosdis.nasa.gov)
# SENDGRID_API_KEY=               # Email alerts (https://sendgrid.com)
# SENDGRID_FROM_EMAIL=alerts@yourdomain.com
```

### Frontend

Create `frontend/.env.local` (copy from `frontend/.env.example`):

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-public-key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

> **Note:** Maps use Leaflet + OpenStreetMap — no Mapbox token needed.

---

## Step 4 — Install Dependencies

### Option A: Docker (skip to Step 5)

Docker handles installation automatically. Jump to Step 5, Option A.

### Option B: Manual

```bash
# Install uv (if not installed)
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS / Linux
# curl -LsSf https://astral.sh/uv/install.sh | sh

# Backend — install dependencies via uv
cd backend
uv sync          # creates .venv and installs all deps from uv.lock

# Frontend
cd ../frontend
npm install
```

---

## Step 5 — Start the Application

### Option A: Docker (one command)

```bash
docker-compose up
```

This starts the frontend, backend, and Redis in one go.

### Option B: Manual (two terminals)

**Terminal 1 — Backend:**
```bash
cd backend
uv run uvicorn main:app --reload
```

You should see:
```
🚀 Starting Disaster Management API...
✅ ML models loaded successfully
✅ Ingestion orchestrator started
✅ Anomaly detection started
✅ Sitrep cron scheduled
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

---

## Step 6 — Verify Everything Works

| Service | URL | Expected |
|---------|-----|----------|
| Frontend | http://localhost:3000 | Landing page with hero section |
| Backend API | http://localhost:8000 | `{"message": "Disaster Management API", "status": "operational"}` |
| Health check | http://localhost:8000/health | `{"status": "healthy", "ml_models_loaded": true}` |
| Swagger docs | http://localhost:8000/docs | Interactive API documentation |

---

## What Works Out of the Box

### Phase 1 — Core Platform
- Register and login with email/password
- Create, view, update, and delete disaster records
- Interactive Leaflet map with live disaster markers
- Run ML predictions (severity, spread, impact)
- Manage resource inventory
- Role-based dashboards (Admin, Victim, NGO, Coordinator)

### Phase 2 — Resource Allocation
- LP-optimized allocation engine (maximizes coverage, minimizes distance)
- Resource shortfall forecasting (predict demand vs supply)

### Phase 3 — NLP Triage & Chatbot
- Submit resource requests in plain text — auto-classified to type + priority
- AI chatbot walks victims through a guided intake conversation
- Coordinators can override and correct NLP results (training feedback)

### Phase 4 — Data Ingestion
- Background orchestrator polls external feeds (weather, GDACS, USGS, FIRMS)
- Ingested events shown in dashboard with alert notifications
- Works without API keys: GDACS and USGS feeds are free and keyless

### Phase 5 — AI Coordinator Dashboard
- Generate situation reports (daily cron or on-demand)
- Ask questions in natural language ("How many active disasters?")
- Anomaly detection runs in background (Isolation Forest)
- Track prediction outcomes vs actual results
- Model accuracy evaluation reports

---

## Role-Based Dashboards

| Role | Dashboard Path | Capabilities |
|------|---------------|-------------|
| **Admin** | `/admin/live-map` | Full system access, live monitoring |
| **Coordinator** | `/dashboard/coordinator` | Sitreps, NL queries, anomalies, outcome tracking |
| **NGO / Donor** | `/ngo/inventory`, `/ngo/requests` | Manage resource inventory, review victim requests |
| **Victim** | `/victim` | Submit requests, use chatbot, track request status |

---

## Optional API Keys (All Free)

These enhance functionality but are **not required**:

| Key | Free Tier | What You Get | Signup |
|-----|-----------|-------------|--------|
| `OPENWEATHERMAP_API_KEY` | 1,000 calls/day | Real weather data for predictions | [openweathermap.org](https://openweathermap.org/api) |
| `FIRMS_API_KEY` | Unlimited | NASA satellite fire hotspot data | [firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov/api/area/) |
| `SENDGRID_API_KEY` | 100 emails/day | Email delivery for critical alerts | [sendgrid.com](https://sendgrid.com) |

**Without these keys:** Weather/FIRMS polling is silently skipped, alerts are stored in the database (visible on dashboard) but no emails are sent. All other features work normally.

---

## Troubleshooting

### Backend won't start

**"Missing Supabase credentials"**
- Ensure `backend/.env` exists and has `SUPABASE_URL`, `SUPABASE_KEY`, and `SUPABASE_SERVICE_KEY` set to real values (not the placeholder text)

**"ML models loaded" doesn't appear**
- Check that `backend/models/` contains `.pkl` files. If missing, run:
  ```bash
  cd backend
  uv run python scripts/generate_training_data.py
  uv run python -m app.services.training.train_all
  ```

**Database connection errors**
- Verify `DATABASE_URL` uses the correct password and host (`db.your-project.supabase.co`, not `your-project.supabase.co`)
- Ensure `+asyncpg` is in the URL prefix: `postgresql+asyncpg://...`

### Frontend won't start

**Module not found errors**
```bash
cd frontend
rm -rf node_modules .next
npm install
npm run dev
```

**Blank page / API errors**
- Verify `frontend/.env.local` has the correct Supabase URL and anon key
- Confirm backend is running on port 8000

### Real-time updates not working
- In Supabase Dashboard → **Database → Replication**, enable realtime for the tables you need
- Check browser console for WebSocket connection errors

### Docker issues
- Ensure Docker Desktop is running
- Try `docker-compose down -v` then `docker-compose up --build`

---

## Verification Checklist

Once setup is complete, confirm each feature:

- [ ] Can register a new user and login
- [ ] Landing page loads at `localhost:3000`
- [ ] Backend health check returns `ml_models_loaded: true`
- [ ] Can create a disaster from the dashboard
- [ ] Disaster appears on the map
- [ ] Can run a prediction (severity/spread/impact)
- [ ] Can submit a victim resource request
- [ ] Chatbot responds at `/victim/requests/chatbot`
- [ ] Swagger docs load at `localhost:8000/docs`
- [ ] Can generate a situation report from coordinator dashboard

---

## What's Next

| Goal | Action |
|------|--------|
| Explore the API | Visit http://localhost:8000/docs and try endpoints interactively |
| Test real-time | Open the app in two browser tabs and create a disaster — both tabs update live |
| Add API keys | Sign up for free keys and add to `backend/.env` for weather/fire/email features |
| Deploy | Read [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment guide |
| Retrain models | `POST /api/ml/retrain` to trigger model retraining with new data |
| Customize | Modify components in `frontend/src/components/`, add new routers in `backend/app/routers/` |

---

**You're all set. Happy building!**
