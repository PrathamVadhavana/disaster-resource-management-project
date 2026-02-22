# Disaster Resource Management System

An end-to-end, AI-powered platform for disaster monitoring, prediction, victim assistance, and intelligent resource allocation — built across **five integrated development phases**.

> **Zero paid APIs required.** Every ML model, NLP pipeline, and AI feature runs locally using scikit-learn, PuLP, and rule-based engines. Optional free-tier integrations (OpenWeatherMap, NASA FIRMS, SendGrid) enhance functionality but are not mandatory.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Client Browser                            │
│            Next.js · TypeScript · Tailwind CSS · Leaflet         │
│   Landing ─ Auth ─ Admin ─ Victim ─ NGO ─ Coordinator Dashboards │
└──────────────────────┬───────────────────────────────────────────┘
                       │ HTTPS / WebSocket
┌──────────────────────▼───────────────────────────────────────────┐
│                    Supabase Platform                              │
│   Auth (JWT)  ·  PostgreSQL + PostGIS  ·  Realtime (WebSocket)   │
│   Row-Level Security  ·  Edge Functions                          │
└──────────────────────┬───────────────────────────────────────────┘
                       │ REST / async
┌──────────────────────▼───────────────────────────────────────────┐
│                   FastAPI Backend                                 │
│  ┌───────────┐ ┌───────────────┐ ┌──────────────┐ ┌───────────┐ │
│  │ ML Models │ │  Allocation   │ │  NLP Triage  │ │ Ingestion │ │
│  │ (sklearn) │ │ Engine (PuLP) │ │  & Chatbot   │ │ Orchestr. │ │
│  └───────────┘ └───────────────┘ └──────────────┘ └───────────┘ │
│  ┌───────────┐ ┌───────────────┐ ┌──────────────┐               │
│  │ Anomaly   │ │  Sitrep &     │ │  Outcome     │               │
│  │ Detection │ │  NL Queries   │ │  Tracking    │               │
│  └───────────┘ └───────────────┘ └──────────────┘               │
└──────────────────────────────────────────────────────────────────┘
           │
     ┌─────▼─────┐
     │   Redis    │  (optional — caching)
     └───────────┘
```

---

## Development Phases

| Phase | Name | Highlights |
|:-----:|------|------------|
| **1** | Core Platform | Auth, disaster/resource CRUD, ML predictions (severity · spread · impact), interactive Leaflet map, role-based dashboards |
| **2** | Allocation Engine | PuLP mixed-integer linear programming optimizer, resource shortfall forecasting (sklearn + optional Prophet) |
| **3** | NLP Triage & Chatbot | Rule-based auto-classification of victim requests, urgency extraction, 8-state conversational chatbot, coordinator override feedback loop |
| **4** | Real-Time Ingestion | Background orchestrator polling OpenWeatherMap, GDACS, USGS earthquakes, NASA FIRMS fire hotspots, social media; automated alert pipeline |
| **5** | AI Coordinator | Situation report generation (daily cron + on-demand), natural-language "chat with your data" queries, Isolation Forest anomaly detection, outcome tracking, model evaluation reports |

---

## Features

### AI & Machine Learning
- **Severity prediction** — classify disaster severity from environmental features
- **Spread prediction** — estimate affected area (km²) with confidence intervals
- **Impact prediction** — forecast casualties and economic damage (USD)
- **Resource allocation optimizer** — MILP via PuLP maximizing coverage × urgency, minimizing delivery distance
- **Resource shortfall forecasting** — linear regression + optional Prophet time-series
- **Anomaly detection** — Isolation Forest detecting consumption spikes, request volume anomalies, severity escalation
- **Model retraining pipeline** — background or synchronous retraining with automatic hot-reload

### NLP & Conversational AI
- **Auto-triage** — classify free-text victim requests into resource type + priority + estimated quantity
- **Urgency extraction** — NER-style keyword detection with severity boost scores
- **AI Chatbot** — multi-step conversational intake (situation → resource → quantity → location → people → medical → confirm)
- **Natural language queries** — ask questions in plain English against your operational data

### Data Ingestion (Phase 4)
- **Weather** — OpenWeatherMap current conditions (free tier: 1,000 calls/day)
- **Earthquakes** — USGS real-time GeoJSON feed (free, no key)
- **Disasters** — GDACS RSS feed (free, no key)
- **Fire hotspots** — NASA FIRMS satellite data (free key)
- **Social media** — Twitter/X keyword monitoring (optional paid API)
- **Alerting** — SendGrid email delivery (free tier: 100/day) with log-only fallback

### Coordinator Dashboard (Phase 5)
- **Situation reports** — auto-generated daily or on-demand markdown reports
- **Anomaly alerts** — acknowledge, resolve, or flag as false positive
- **Outcome tracking** — compare predictions against actual outcomes
- **Model evaluation** — accuracy reports across all prediction types

### Frontend
- Role-based dashboards: **Admin**, **Victim**, **NGO/Donor**, **Coordinator**
- Interactive Leaflet/OpenStreetMap disaster map (no API key needed)
- Real-time updates via Supabase WebSocket subscriptions
- Dark/light theme, responsive mobile-first design
- Victim resource request form with AI chatbot alternative

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js · React · TypeScript · Tailwind CSS · Leaflet · Zustand · React Query |
| Backend | FastAPI · Python 3.11 · Uvicorn · Pydantic |
| Database | Supabase (PostgreSQL + PostGIS) · SQLAlchemy (async) |
| ML/AI | scikit-learn · XGBoost · PuLP · Prophet (optional) · pandas · NumPy |
| Infra | Docker · Docker Compose · Redis (optional) |
| Integrations | OpenWeatherMap · USGS · GDACS · NASA FIRMS · SendGrid (all free tier) |

---

## Quick Start

> See [GETTING_STARTED.md](GETTING_STARTED.md) for a detailed step-by-step walkthrough with screenshots and troubleshooting.

### Prerequisites

- **Node.js 20+** and **npm**
- **Python 3.11+** and **pip**
- **Supabase** account ([free tier](https://supabase.com))
- **Docker** (optional — for one-command setup)

### 1. Setup Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. In the **SQL Editor**, run these scripts in order:
   - `database/schema.sql` — core tables
   - `database/phase2_allocation_engine.sql` — allocation tables
   - `database/phase3_nlp_triage.sql` — NLP feedback table
   - `database/create_resource_requests.sql` — victim request tables
   - `database/phase4_realtime_ingestion.sql` — ingestion tables
   - `database/phase5_ai_coordinator.sql` — coordinator tables
   - `database/seed_available_resources.sql` — sample resource data (optional)
3. Copy your **Project URL**, **Anon Key**, and **Service Role Key** from **Settings → API**

### 2. Configure Environment

**Backend** — create `backend/.env`:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_DB_PASSWORD=your-db-password
DATABASE_URL=postgresql+asyncpg://postgres:your-db-password@db.your-project.supabase.co:5432/postgres
ALLOWED_ORIGINS=http://localhost:3000
DEBUG=true
```

**Frontend** — create `frontend/.env.local`:
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Install & Run

**Option A — Docker (one command):**
```bash
docker-compose up
```

**Option B — Manual:**
```bash
# Install uv (one-time)
# Windows: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS / Linux: curl -LsSf https://astral.sh/uv/install.sh | sh

# Terminal 1: Backend
cd backend
uv sync              # creates .venv and installs all deps
uv run uvicorn main:app --reload

# Terminal 2: Frontend
cd frontend
npm install
npm run dev
```

### 4. Open the App

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |

---

## API Reference

### Authentication — `/api/auth`
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/register` | Register new user |
| POST | `/login` | Login and get JWT |
| GET | `/me` | Get current user profile |
| POST | `/logout` | Invalidate session |

### Disasters — `/api/disasters`
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List disasters (filter, paginate) |
| GET | `/{id}` | Get disaster by ID |
| POST | `/` | Create disaster |
| PATCH | `/{id}` | Update disaster |
| DELETE | `/{id}` | Soft-delete disaster |
| GET | `/{id}/resources` | Resources allocated to disaster |

### Predictions — `/api/predictions`
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/` | Run single prediction (severity/spread/impact) |
| GET | `/` | List predictions |
| GET | `/{id}` | Get prediction detail |
| POST | `/batch` | Run batch predictions |

### Resources — `/api/resources`
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List resources |
| POST | `/` | Create resource |
| PATCH | `/{id}` | Update resource |
| POST | `/allocate` | Run LP-optimized allocation |
| POST | `/{id}/deallocate` | Free allocated resource |
| GET | `/forecast` | Predict resource shortfall |

### Victim — `/api/victim`
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/requests` | Create resource request (auto NLP triage) |
| GET | `/requests` | List victim's requests |
| GET | `/requests/{id}` | Get request detail |
| PUT | `/requests/{id}` | Update pending request |
| DELETE | `/requests/{id}` | Cancel request |
| GET | `/dashboard-stats` | Aggregated victim stats |
| GET | `/available-resources` | Browse available inventory |
| GET | `/profile` | Get victim profile |
| PUT | `/profile` | Update profile |
| PUT | `/profile/location` | Update GPS location |

### NLP Triage & Chatbot — `/api/nlp`
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/classify` | Classify text → resource type + priority |
| POST | `/extract-urgency` | Extract urgency keywords |
| POST | `/chatbot` | Send message to AI chatbot |
| GET | `/chatbot/{session_id}` | Get chatbot session |
| DELETE | `/chatbot/{session_id}` | End chatbot session |
| POST | `/override` | Coordinator correction feedback |

### Data Ingestion — `/api/ingestion`
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Health of all data feeds |
| POST | `/poll/{source}` | Manually trigger feed poll |
| POST | `/start` | Start background orchestrator |
| POST | `/stop` | Stop background orchestrator |
| GET | `/events` | List ingested events |
| GET | `/weather` | Weather observations |
| GET | `/satellites` | Satellite/fire hotspot data |
| GET | `/alerts` | Alert notifications |

### AI Coordinator — `/api/coordinator`
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sitrep/generate` | Generate situation report |
| GET | `/sitrep` | List reports |
| GET | `/sitrep/latest` | Latest report |
| POST | `/query` | Natural language data query |
| GET | `/anomalies` | List anomaly alerts |
| GET | `/anomalies/active` | Active unacknowledged anomalies |
| POST | `/anomalies/detect` | Trigger anomaly detection |
| POST | `/outcomes` | Log actual outcome |
| POST | `/outcomes/evaluate` | Generate evaluation report |
| GET | `/outcomes/accuracy` | Accuracy summary |

### ML Models — `/api/ml`
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/info` | Model version & metadata |
| POST | `/retrain` | Trigger async retraining |
| POST | `/retrain-sync` | Trigger sync retraining |

Full interactive docs at **http://localhost:8000/docs**

---

## Project Structure

```
disaster-resource-management/
├── frontend/                          # Next.js application
│   ├── src/
│   │   ├── app/                      # Pages & routing
│   │   │   ├── (auth)/              # Login & signup flows
│   │   │   ├── (dashboard)/         # Role-based dashboards
│   │   │   │   ├── admin/           # Admin live map
│   │   │   │   ├── victim/          # Victim requests, chatbot, profile
│   │   │   │   ├── ngo/             # NGO inventory & request management
│   │   │   │   └── allocation/      # Resource allocation view
│   │   │   └── dashboard/           # Shared dashboard pages
│   │   │       ├── coordinator/     # AI coordinator (sitreps, NL query, anomalies)
│   │   │       ├── disasters/       # Disaster management
│   │   │       ├── predictions/     # ML prediction viewer
│   │   │       └── resources/       # Resource management
│   │   ├── components/              # React components
│   │   │   ├── auth/               # Auth forms & onboarding
│   │   │   ├── coordinator/        # Sitrep, NL query, anomaly, outcome panels
│   │   │   ├── dashboard/          # Ingestion status, live impact map
│   │   │   ├── landing/            # Hero, role cards, impact map, ticker
│   │   │   ├── map/                # Leaflet disaster map
│   │   │   ├── victim/             # Request form, chatbot, profile, dashboard
│   │   │   └── ui/                 # Base UI primitives
│   │   ├── lib/                    # Supabase client, auth, API, store, utils
│   │   ├── hooks/                  # Custom React hooks
│   │   └── types/                  # TypeScript definitions
│   ├── Dockerfile
│   └── package.json
│
├── backend/                           # FastAPI application
│   ├── app/
│   │   ├── routers/                 # 10 API route modules
│   │   ├── services/                # Business logic & AI engines
│   │   │   ├── ml_service.py        # Prediction models (sklearn)
│   │   │   ├── allocation_engine.py # MILP optimizer (PuLP)
│   │   │   ├── forecast_service.py  # Resource shortfall forecasting
│   │   │   ├── nlp_service.py       # Text classification & urgency extraction
│   │   │   ├── chatbot_service.py   # Conversational state machine
│   │   │   ├── anomaly_service.py   # Isolation Forest anomaly detection
│   │   │   ├── sitrep_service.py    # Situation report generator
│   │   │   ├── nl_query_service.py  # Natural language → DB queries
│   │   │   ├── outcome_service.py   # Prediction vs actual tracking
│   │   │   └── ingestion/           # External feed pollers
│   │   ├── core/                    # Configuration (Phase 4 & 5)
│   │   ├── database.py              # Supabase + SQLAlchemy setup
│   │   └── schemas.py               # Pydantic models
│   ├── models/                      # Trained ML models (.pkl + metadata)
│   ├── training_data/               # CSV datasets for retraining
│   ├── scripts/                     # Data generation & training scripts
│   ├── tests/                       # Unit & integration tests
│   ├── Dockerfile
│   ├── main.py                      # Entry point with lifespan events
│   ├── pyproject.toml               # Project metadata & deps (uv)
│   └── uv.lock                      # Reproducible lock file
│
├── database/                          # SQL migrations
│   ├── schema.sql                   # Core tables (Phase 1)
│   ├── phase2_allocation_engine.sql # Consumption log
│   ├── phase3_nlp_triage.sql        # NLP feedback
│   ├── phase4_realtime_ingestion.sql# Ingestion tables
│   ├── phase5_ai_coordinator.sql    # Coordinator tables
│   ├── seed_available_resources.sql # Sample resource data
│   └── *.sql                        # Additional migration & fix scripts
│
├── docs/                              # Additional documentation
│   ├── API.md
│   ├── DEPLOYMENT.md
│   ├── DEVELOPMENT.md
│   └── PHASE4_INGESTION.md
│
├── docker-compose.yml                 # Frontend + Backend + Redis
├── GETTING_STARTED.md                 # Detailed setup walkthrough
└── README.md                          # This file
```

---

## Database Schema

### Core Tables
| Table | Purpose |
|-------|---------|
| `locations` | Geographic points (cities, shelters, hospitals, warehouses) with PostGIS |
| `disasters` | Events with type, severity, status, casualties, damage estimates |
| `resources` | Resource inventory with type, quantity, priority, allocation status |
| `predictions` | ML prediction records with confidence scores |
| `users` / `profiles` | User accounts and role-based profiles |
| `victim_details` | Extended victim info (medical needs, household size, GPS) |
| `resource_requests` | Victim requests with NLP-assigned type/priority |
| `available_resources` | Browseable inventory for victims (Food, Water, Medical, Shelter, Clothes) |

### Phase 2–5 Tables
| Table | Phase | Purpose |
|-------|:-----:|---------|
| `resource_consumption_log` | 2 | Historical consumption for forecasting |
| `nlp_training_feedback` | 3 | Coordinator overrides for model improvement |
| `external_data_sources` | 4 | Registered feed source configuration |
| `ingested_events` | 4 | Raw events from external feeds |
| `weather_observations` | 4 | Weather data points |
| `satellite_observations` | 4 | Fire/hotspot records |
| `alert_notifications` | 4 | Generated alerts |
| `situation_reports` | 5 | Auto-generated sitreps |
| `nl_query_log` | 5 | Natural language query history |
| `anomaly_alerts` | 5 | Detected anomalies |
| `outcome_tracking` | 5 | Predicted vs actual outcomes |
| `model_evaluation_reports` | 5 | Model accuracy evaluations |

**Extensions:** `uuid-ossp`, `postgis`
**Security:** Row-Level Security (RLS) enabled on all core tables.

---

## Security

- **Authentication** — JWT-based via Supabase Auth with bcrypt password hashing
- **Authorization** — Row-Level Security policies + role-based access control (admin, coordinator, ngo, donor, victim)
- **Data protection** — HTTPS in production, CORS configuration, Pydantic input validation
- **Environment isolation** — all secrets via `.env` files, never committed to source control

---

## Testing

```bash
# Backend unit & integration tests
cd backend
pytest
pytest --cov=app tests/    # with coverage report

# Frontend
cd frontend
npm run lint               # ESLint
npm run build              # type-check + build
```

---

## Deployment

| Component | Recommended Platform |
|-----------|---------------------|
| Frontend | Vercel, Netlify, or any Node.js host |
| Backend | Railway, Fly.io, Render, or any Docker host |
| Database | Supabase Cloud (already hosted) |

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed instructions.

---

## Optional Free API Keys

All features work without these keys (graceful degradation), but they unlock additional capabilities:

| Service | Free Tier | What It Enables |
|---------|-----------|-----------------|
| [OpenWeatherMap](https://openweathermap.org/api) | 1,000 calls/day | Weather data ingestion |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/) | Unlimited | Satellite fire hotspot data |
| [SendGrid](https://sendgrid.com) | 100 emails/day | Email alert delivery |

Maps use **Leaflet + OpenStreetMap** — completely free, no key needed.

---

## License

This project is licensed under the MIT License.

---

**Built for disaster preparedness and response.**
