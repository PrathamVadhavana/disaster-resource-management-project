# DisasterGPT — Full Tutorial

Complete guide to running and using DisasterGPT, your AI-powered disaster management assistant.

**Time required:** ~15 minutes (including setup)

---

## What is DisasterGPT?

DisasterGPT is an AI assistant embedded in the disaster management platform that can:
- Answer questions about active disasters, resources, and requests using **live data**
- Stream responses in real-time (SSE)
- Generate inline charts and visualizations
- Execute actions directly (allocate resources, generate reports)
- Provide follow-up suggestions to guide your analysis
- Send daily auto-digest briefings
- Proactively alert you about anomalies

---

## Prerequisites

Before running DisasterGPT, complete the base setup from [GETTING_STARTED.md](GETTING_STARTED.md):

| Requirement | Purpose |
|-------------|---------|
| Supabase project | Database for sessions, messages, action logs |
| Backend running on port 8000 | API server with LLM router |
| Frontend running on port 3000 | Chat UI component |
| `GROQ_API_KEY` | Free LLM inference (Llama 3.3 70B) |

---

## Step 1 — Get a Free Groq API Key

DisasterGPT uses **Groq** for fast, free LLM inference with Llama 3.3 70B.

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up or log in
3. Go to **API Keys** → Create a new key
4. Copy the key (starts with `gsk_...`)

---

## Step 2 — Configure Environment Variables

### Backend (`backend/.env`)

Add these lines to your existing `.env` file:

```env
# DisasterGPT LLM Configuration
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Optional: ChromaDB persistence directory
CHROMA_PERSIST_DIR=models/chroma_db
```

### Frontend (`frontend/.env.local`)

Ensure this is set:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Step 3 — Run the Database Migration

DisasterGPT requires new tables for persistent sessions, messages, action logs, and digest subscriptions.

### Option A: Via Supabase Dashboard

1. Go to your Supabase project → **SQL Editor**
2. Open `database/migrations/014_disastergpt_enhancements.sql`
3. Copy the entire contents and paste into the SQL Editor
4. Click **Run**

### Option B: Via Supabase CLI

```bash
supabase db push
```

### Verify Tables Were Created

Run this in the SQL Editor:

```sql
SELECT table_name FROM information_schema.tables 
WHERE table_name LIKE 'disastergpt_%';
```

You should see:
- `disastergpt_sessions`
- `disastergpt_messages`
- `disastergpt_digest_subscriptions`
- `disastergpt_digest_log`
- `disastergpt_action_log`
- `disastergpt_alert_subscriptions`

---

## Step 4 — Index the Knowledge Base (First Time Only)

DisasterGPT uses ChromaDB for RAG (Retrieval-Augmented Generation). Index your data:

```bash
cd backend

# Index disasters from database + training data
uv run python -m ml.disaster_rag index
```

Or trigger via API:

```bash
curl -X POST http://localhost:8000/api/llm/index \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## Step 5 — Start the Application

### Terminal 1 — Backend

```bash
cd backend
uv run uvicorn main:app --reload
```

Expected output:
```
🚀 Starting Disaster Management API...
✅ ML models loaded successfully
✅ Ingestion orchestrator started
✅ Anomaly detection started
✅ Sitrep cron scheduled
```

### Terminal 2 — Frontend

```bash
cd frontend
npm run dev
```

---

## Step 6 — Access DisasterGPT

### Option A: Floating Chat Widget (All Pages)

1. Open http://localhost:3000
2. Log in with your account
3. Look for the **blue/purple floating button** in the bottom-right corner
4. Click it to open the chat panel

### Option B: Dedicated Chat Page

Navigate to any dashboard page — the `ChatWidget` component is available globally.

---

## How to Use DisasterGPT

### Basic Queries

Just type natural language questions:

```
"How many active disasters are there?"
"What resources are running low?"
"Show me pending requests"
"Which areas have the most requests?"
```

### Admin Briefing

Type one of these:
```
"Give me an admin briefing"
"What needs attention?"
"Daily brief"
```

DisasterGPT will analyze stale requests, critical shortages, chatbot abandonment, anomaly alerts, and more.

### Resource Gap Analysis

```
"Where are our biggest resource gaps?"
"Supply vs demand"
"What are we short on?"
```

Returns a table with demand, supply, gap, and coverage percentage for each resource type.

### Trend Analysis

```
"Are things getting better or worse?"
"Show me trends"
"Week over week comparison"
```

Displays bar charts comparing this week vs last week for request volume, user signups, and completions.

### Geographic Insights

```
"Which areas have the most requests?"
"Show me underserved regions"
"Geographic distribution"
```

### Disaster Scorecards

```
"Compare disaster performance scorecards"
"Which disaster is worst?"
"Disaster health scores"
```

### Comprehensive Digest

```
"Give me a comprehensive daily digest"
"Full summary of everything"
"Complete overview"
```

Generates a multi-section report covering trends, disasters, requests, shortages, scorecards, engagement, alerts, and underserved areas.

---

## DisasterGPT Features

### 1. Streaming Responses

Responses stream in real-time as the LLM generates them — tokens appear progressively for instant feedback.

### 2. Follow-Up Suggestion Chips

After each response, DisasterGPT shows 3 clickable suggestion chips:
- Click a chip to instantly ask that follow-up question
- Suggestions are context-aware based on the previous answer

### 3. Action Cards

When DisasterGPT detects an actionable situation (e.g., critical resource shortage), it shows an action card with a confirm button:
- **Allocate Now** — directly allocates resources to a disaster
- **Generate Report** — triggers SITREP generation
- **Review Stale** — shows details of stuck requests

Click the button to execute the action immediately. Results are shown inline.

### 4. Inline Charts

DisasterGPT automatically renders charts for:
- Trend comparisons (bar chart)
- Supply vs demand (grouped bar chart)
- Request pipeline funnel (horizontal bar chart)
- Disaster scorecards (grouped bar chart)
- Geographic distribution (bar chart)

### 5. CSV Export

For geographic, disaster comparison, responder performance, and pipeline data, a **"Export as CSV"** button appears below the chart. Click to download the data.

### 6. Search Messages

Click the 🔍 icon in the header to search through conversation history.

### 7. Quick Actions

Click the ⚡ icon to see a grid of one-click quick actions:
- Briefing, Resource Gaps, Trends, Geography, Scorecards, Digest

### 8. Export Chat

Click the ⬇️ icon to download the entire conversation as a `.txt` file.

### 9. Clear Chat

Click the 🗑️ icon to start a fresh session (generates new session ID).

---

## API Endpoints Reference

### Chat

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/llm/chat` | POST | Send a message, get full response |
| `/api/llm/chat/stream` | POST | Send a message, get streaming SSE response |
| `/api/llm/sessions/{id}` | GET | Get session history |
| `/api/llm/sessions/{id}` | DELETE | Delete a session |

### Actions

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/llm/actions/execute` | POST | Execute an action (allocate, generate report, acknowledge alert) |

### Digest

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/llm/digest/subscribe` | POST | Subscribe to daily auto-digest |
| `/api/llm/digest/unsubscribe` | DELETE | Unsubscribe from digest |
| `/api/llm/digest/history` | GET | View past digests |
| `/api/llm/digest/run` | POST | Trigger digest generation (admin only) |

### Alerts

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/llm/alerts/proactive` | GET | Get proactive anomaly-based insights |

### Knowledge Base

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/llm/query` | POST | Submit a RAG query |
| `/api/llm/stream` | POST | Streaming RAG query |
| `/api/llm/index` | POST | Re-index knowledge base (admin only) |
| `/api/llm/stats` | GET | Knowledge base statistics |

---

## Example API Calls

### Send a Chat Message

```bash
curl -X POST http://localhost:8000/api/llm/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "message": "Give me an admin briefing",
    "user_context": {
      "role": "admin",
      "name": "John Doe",
      "user_id": "user-uuid-here"
    }
  }'
```

### Stream a Chat Response

```bash
curl -N -X POST http://localhost:8000/api/llm/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "message": "Show me the supply-demand gaps"
  }'
```

### Execute an Action

```bash
curl -X POST http://localhost:8000/api/llm/actions/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "action_type": "allocate_resources",
    "action_payload": {
      "disaster_id": "disaster-uuid",
      "resource_type": "water",
      "quantity_needed": 500
    }
  }'
```

### Subscribe to Daily Digest

```bash
curl -X POST http://localhost:8000/api/llm/digest/subscribe \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "digest_time": "08:00",
    "timezone": "Asia/Kolkata"
  }'
```

### Get Proactive Alerts

```bash
curl http://localhost:8000/api/llm/alerts/proactive \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## Architecture Overview

```
User types message
        │
        ▼
┌─────────────────┐
│  Frontend (TSX) │
│  DisasterGPT.tsx│
└────────┬────────┘
         │ POST /api/llm/chat (or /chat/stream)
         ▼
┌─────────────────────────────────┐
│  Backend (llm.py Router)        │
│                                 │
│  1. _classify_intent()          │ ← Semantic (sentence-transformers)
│  2. _prune_context_by_intent()  │ ← Only fetch relevant data
│  3. _get_full_context()         │ ← Parallel Supabase queries
│  4. Route to intent handler     │ ← 20+ specialized handlers
│  5. _generate_follow_ups()      │ ← Context-aware suggestions
│  6. _generate_action_cards()    │ ← Actionable recommendations
│  7. _persist_message()          │ ← Save to DB (background)
│  8. _update_summary()           │ ← LLM conversation summary
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  LLM Backend (Groq / Local)    │
│  - Llama 3.3 70B (free tier)   │
│  - Or local GGUF model         │
│  - Or rule-based fallback      │
└─────────────────────────────────┘
```

---

## Troubleshooting

### "GROQ_API_KEY env var not set"

Add your Groq API key to `backend/.env`:
```env
GROQ_API_KEY=gsk_your_key_here
```

Then restart the backend.

### "Session not found" (404)

The session may have been cleared. Click the 🗑️ button to create a new session.

### "Stream request failed"

- Ensure backend is running on port 8000
- Check `NEXT_PUBLIC_API_URL` in `frontend/.env.local`
- Check browser console for CORS errors

### "Action execution failed"

- Verify you have admin or coordinator role
- Check that the disaster_id exists in the database
- Check backend logs for detailed error

### Charts not rendering

- Ensure `recharts` is installed: `npm install recharts`
- Check browser console for JavaScript errors

### Slow responses

- First response is slower (model warmup)
- Intent-based pruning should make subsequent queries faster
- Check if GROQ_API_KEY is set (without it, falls back to rule-based which is faster but less capable)

### "No history found"

- Sessions are persisted to Supabase only after the migration is run
- Verify `disastergpt_sessions` and `disastergpt_messages` tables exist
- Check Supabase connection in `backend/.env`

---

## Performance Tips

1. **Use specific intents** — "Show me supply-demand gaps" is faster than "Tell me everything about resources"
2. **Streaming by default** — Responses stream in real-time for instant feedback
3. **Prune context** — The system automatically prunes context by intent, reducing token usage by 60-80%

---

**You're ready to use DisasterGPT! Try asking: "Give me an admin briefing"**