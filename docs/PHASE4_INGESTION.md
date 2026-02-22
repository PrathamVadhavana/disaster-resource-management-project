# Phase 4: Real-Time Data Ingestion & Disaster Alerting

## Overview

Phase 4 connects the platform to live external data sources so ML predictions are grounded in real-world conditions. The system continuously polls five feeds, auto-creates disaster records, triggers batch predictions, pushes results to the frontend via Supabase Realtime, and dispatches critical-severity alerts to NGOs.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    IngestionOrchestrator                          │
│  (async background loops inside FastAPI lifespan)                │
│                                                                  │
│  ┌───────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  ┌────┐ │
│  │ Weather   │  │ GDACS    │  │ USGS     │  │ FIRMS  │  │Soc.│ │
│  │ (600s)    │  │ (900s)   │  │ (300s)   │  │ (1800s)│  │(300)│ │
│  └─────┬─────┘  └────┬─────┘  └────┬─────┘  └───┬────┘  └──┬─┘ │
│        │              │             │             │          │    │
│        ▼              ▼             ▼             ▼          ▼    │
│   weather_obs    ingested_events  ingested_events  sat_obs  ing. │
│                       │             │                        │    │
│                       ▼             ▼                        ▼    │
│               ┌──────────────────────────────┐                   │
│               │   Auto-create disaster       │                   │
│               │   → batch predictions        │                   │
│               │   → alert if critical        │                   │
│               └──────────────────────────────┘                   │
└──────────────────────────────────────────────────────────────────┘
        │                                          │
        ▼                                          ▼
  Supabase Realtime                        SendGrid (free tier)
  (WebSocket → frontend)                   (email alerts)
        │
        ▼
  LiveImpactMap.tsx
  (auto-updating markers)
```

---

## Database Schema

Run **`database/phase4_realtime_ingestion.sql`** in the Supabase SQL editor (or via psql).

| Table                    | Purpose                                           |
| ------------------------ | ------------------------------------------------- |
| `external_data_sources`  | Registry of feed endpoints + poll intervals        |
| `ingested_events`        | Raw events from any source (deduplicated)          |
| `weather_observations`   | Structured weather cache for prediction features   |
| `satellite_observations` | Fire/flood hotspots from NASA FIRMS                |
| `alert_notifications`    | Audit log for email alerts sent to NGOs        |

All tables have RLS enabled (authenticated read, service-role full access) and are added to the `supabase_realtime` publication.

---

## Backend Services

### Service Files (all under `backend/app/services/ingestion/`)

| File                  | Feed                | Poll Interval | API Key Required          |
| --------------------- | ------------------- | ------------- | ------------------------- |
| `weather_service.py`  | OpenWeatherMap      | 600s          | `OPENWEATHERMAP_API_KEY`  |
| `gdacs_service.py`    | GDACS RSS           | 900s          | None (public)             |
| `usgs_service.py`     | USGS Earthquakes    | 300s          | None (public)             |
| `firms_service.py`    | NASA FIRMS          | 1800s         | `FIRMS_API_KEY`           |
| `social_service.py`   | Twitter/X v2 Search | 300s          | `TWITTER_BEARER_TOKEN` (optional, paid) |
| `alert_service.py`    | Notifications       | —             | SendGrid key (free tier)    |
| `orchestrator.py`     | Unified scheduler   | —             | —                         |

### Orchestrator

`IngestionOrchestrator` starts as part of FastAPI's lifespan. Each feed runs in its own `asyncio.Task` loop. New GDACS/USGS events automatically:

1. Create a disaster record (or find a nearby existing one)
2. Run severity + spread + impact batch predictions via MLService
3. If predicted severity = critical → dispatch email via `AlertNotificationService` (SendGrid free tier)

### API Router (`backend/app/routers/ingestion.py`)

| Method  | Endpoint                             | Description                            |
| ------- | ------------------------------------ | -------------------------------------- |
| GET     | `/api/ingestion/status`              | All feed statuses                      |
| POST    | `/api/ingestion/poll/{source_name}`  | Manually trigger one feed              |
| POST    | `/api/ingestion/start`               | Start orchestrator                     |
| POST    | `/api/ingestion/stop`                | Stop orchestrator                      |
| GET     | `/api/ingestion/events`              | List ingested events (filterable)      |
| GET     | `/api/ingestion/events/{id}`         | Single event detail                    |
| GET     | `/api/ingestion/weather`             | Weather observations                   |
| GET     | `/api/ingestion/weather/latest/{id}` | Latest weather for a location          |
| GET     | `/api/ingestion/satellites`          | Satellite/fire observations            |
| GET     | `/api/ingestion/alerts`              | Alert notification log                 |
| GET     | `/api/ingestion/sources`             | Data source registry                   |
| PATCH   | `/api/ingestion/sources/{id}`        | Update source config                   |

---

## Supabase Edge Function

`supabase/functions/notify-disaster/index.ts` — Deno-based edge function that polls the GDACS RSS feed independently (for redundancy). Deploy with:

```bash
supabase functions deploy notify-disaster
```

Schedule it every 15 minutes via the Supabase dashboard (Edge Functions → Schedules).

---

## Frontend

### Components

| Component                                          | Location                                              |
| -------------------------------------------------- | ----------------------------------------------------- |
| `LiveImpactMap`                                    | `frontend/src/components/dashboard/LiveImpactMap.tsx`  |
| `IngestionStatusPanel`                             | `frontend/src/components/dashboard/IngestionStatusPanel.tsx` |

### Hooks

| Hook                | File                                          | Purpose                           |
| ------------------- | --------------------------------------------- | --------------------------------- |
| `useRealtimeEvents` | `frontend/src/hooks/use-realtime-events.ts`   | Supabase Realtime subscription for `ingested_events` |
| `useRealtimeAlerts` | `frontend/src/hooks/use-realtime-events.ts`   | Supabase Realtime subscription for `alert_notifications` |

### Dashboard Page

**`/dashboard/live-map`** — Full-page live impact map with ingestion status panel below.

### How It Works

1. Backend inserts rows into `ingested_events` / `alert_notifications`
2. Supabase Realtime publication pushes changes via WebSocket
3. `useRealtimeEvents` hook receives INSERT events and updates React state
4. `LiveImpactMap` merges live events with historical data and renders markers on a dark Leaflet map
5. Critical alerts show a red banner at the top of the map

---

## Environment Variables

Copy `backend/.env.phase4.example` to your `.env` and fill in keys. Required for full functionality:

| Variable                  | Required | Source                              | Cost       |
| ------------------------- | -------- | ----------------------------------- | ---------- |
| `OPENWEATHERMAP_API_KEY`  | Yes*     | https://openweathermap.org/api      | Free tier  |
| `FIRMS_API_KEY`           | Yes*     | https://firms.modaps.eosdis.nasa.gov | Free       |
| `SENDGRID_API_KEY`        | No       | https://sendgrid.com                | Free tier  |
| `TWITTER_BEARER_TOKEN`    | No       | https://developer.twitter.com       | Paid       |
| `INGESTION_ENABLED`       | No       | Set `false` to disable all polling  | —          |

*Services without API keys will log a warning and skip their poll cycle gracefully.
GDACS and USGS feeds require no API key.

---

## Quick Start

```bash
# 1. Run the database migration
psql -h <SUPABASE_HOST> -U postgres -d postgres -f database/phase4_realtime_ingestion.sql

# 2. Add API keys to .env
cp backend/.env.phase4.example backend/.env  # then edit

# 3. Start services
docker-compose up --build

# 4. Verify ingestion is running
curl http://localhost:8000/api/ingestion/status

# 5. Manually trigger a feed
curl -X POST http://localhost:8000/api/ingestion/poll/usgs

# 6. Open the live map
# Navigate to http://localhost:3000/dashboard/live-map
```
