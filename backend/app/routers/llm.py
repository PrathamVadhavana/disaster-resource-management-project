"""
DisasterGPT — LLM Query API Router (Enhanced)
===============================================
Exposes the RAG-powered LLM assistant as a FastAPI endpoint.

Enhancements (V2):
  1. Persist Chat Sessions to DB (Supabase)
  2. Stream the Chat Endpoint (SSE)
  3. Prune Context by Intent
  4. Semantic Intent Classification (sentence-transformers)
  5. Conversation Memory with Summarization
  6. Follow-Up Suggestion Chips
  7. Action Execution — "Do it, don't just tell me"
  8. Scheduled Auto-Digests — Autopilot briefings at 8 AM daily
  9. Proactive Anomaly Analysis — Auto-push insights when anomalies are detected
  10. ReAct-Style Tool Calling — Turn DisasterGPT into a true autonomous agent
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.database import db, db_admin
from app.dependencies import get_current_user, require_role

logger = logging.getLogger("llm_router")

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────────────────


class LLMQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Natural-language question")
    disaster_id: str | None = Field(None, description="Optional disaster ID for focused context")
    top_k: int = Field(5, ge=1, le=20, description="Number of documents to retrieve")
    max_tokens: int = Field(1024, ge=64, le=4096, description="Max response tokens")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")


class LLMSource(BaseModel):
    content_preview: str
    source: str
    type: str
    relevance: float


class LLMQueryResponse(BaseModel):
    response: str
    sources: list[LLMSource]
    confidence: float
    disaster_id: str | None = None
    documents_retrieved: int = 0


class LLMStatsResponse(BaseModel):
    total_documents: int
    status: str


class LLMIndexResponse(BaseModel):
    indexed: int
    total: int
    message: str


# ── Chat Endpoint Schemas ──────────────────────────────────────────────────────


class ChatContext(BaseModel):
    disaster_id: str | None = None


class UserContext(BaseModel):
    role: str | None = None
    name: str | None = None
    user_id: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    session_id: str | None = Field(None, description="Optional session ID for conversation continuity")
    context: ChatContext | None = Field(None, description="Optional context (e.g., disaster_id)")
    user_context: UserContext | None = Field(None, description="User identity hints from frontend")


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: str


class ChatResponse(BaseModel):
    message: str  # Assistant's response
    session_id: str  # Session ID (new or existing)
    intent: str  # Detected intent category
    context_data: dict | None = None  # Optional context data used for answering
    follow_up_suggestions: list[str] | None = None  # Follow-up question chips
    action_cards: list[dict] | None = None  # Actionable cards with confirm buttons


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    created_at: str
    message_count: int


class ActionExecuteRequest(BaseModel):
    action_type: str = Field(..., description="Type of action to execute")
    action_payload: dict = Field(..., description="Action parameters")
    session_id: str | None = Field(None, description="Optional session ID for context")


class ActionExecuteResponse(BaseModel):
    success: bool
    action_type: str
    result: dict
    message: str


class DigestSubscribeRequest(BaseModel):
    digest_time: str = Field("08:00", description="Time for daily digest (HH:MM)")
    timezone: str = Field("UTC", description="User timezone")


class DigestSubscribeResponse(BaseModel):
    success: bool
    message: str
    next_digest_at: str | None = None


# ── Lazy singleton ──────────────────────────────────────────────────────────────

_rag_instance = None
_semantic_classifier = None


def _get_rag():
    """Lazy-load DisasterRAG to avoid import-time heavyweight init."""
    global _rag_instance
    if _rag_instance is None:
        from ml.disaster_rag import DisasterRAG

        _rag_instance = DisasterRAG()
    return _rag_instance


def _get_semantic_classifier():
    """Lazy-load semantic intent classifier using sentence-transformers."""
    global _semantic_classifier
    if _semantic_classifier is None:
        try:
            from sentence_transformers import SentenceTransformer, util
            import numpy as np

            model = SentenceTransformer("all-MiniLM-L6-v2")

            # Intent exemplars — representative phrases for each intent
            intent_exemplars = {
                "resource_requests": [
                    "how many requests are there",
                    "show me pending requests",
                    "what requests are open",
                    "request count status",
                ],
                "available_resources": [
                    "what resources do we have",
                    "show inventory",
                    "available supplies stock",
                    "what's in our warehouse",
                ],
                "disaster_status": [
                    "what disasters are active",
                    "current emergency status",
                    "which disasters are happening",
                    "show active disasters",
                ],
                "low_stock": [
                    "running low on supplies",
                    "shortage of resources",
                    "what's depleted",
                    "items almost out of stock",
                ],
                "briefing": [
                    "give me a briefing",
                    "what needs attention",
                    "daily admin brief",
                    "critical issues today",
                ],
                "supply_demand_gap": [
                    "resource gap analysis",
                    "supply vs demand",
                    "what are we short on",
                    "biggest supply deficit",
                ],
                "request_lifecycle": [
                    "how fast are requests fulfilled",
                    "stale stuck requests",
                    "fulfillment time bottleneck",
                    "request processing speed",
                ],
                "chatbot_activity": [
                    "chatbot intake activity",
                    "what are victims requesting",
                    "chatbot abandonment rate",
                    "victim chatbot sessions",
                ],
                "activity_heatmap": [
                    "when do we get most requests",
                    "peak hours for requests",
                    "busiest time of day",
                    "request patterns temporal",
                ],
                "engagement": [
                    "user engagement active users",
                    "who is active on platform",
                    "volunteer donor activity",
                    "idle inactive users",
                ],
                "registration_trends": [
                    "new user signups",
                    "registration growth",
                    "who registered recently",
                    "incomplete profiles onboarding",
                ],
                "request_pipeline": [
                    "request pipeline funnel",
                    "completion rate rejection rate",
                    "request journey workflow",
                    "status breakdown funnel",
                ],
                "trends": [
                    "are things getting better",
                    "week over week trends",
                    "improving or declining",
                    "trajectory compared to last week",
                ],
                "geographic": [
                    "which areas have most requests",
                    "geographic distribution location",
                    "underserved regions",
                    "where should we focus resources",
                ],
                "disaster_comparison": [
                    "compare disasters scorecard",
                    "which disaster is worst",
                    "disaster performance health",
                    "disaster comparison ranking",
                ],
                "responder_performance": [
                    "ngo volunteer performance",
                    "who is fastest responder",
                    "best worst ngo",
                    "responder turnaround time",
                ],
                "digest": [
                    "comprehensive daily digest",
                    "full summary everything",
                    "complete overview report",
                    "weekly digest full report",
                ],
                "user_requests": [
                    "my request status",
                    "track my submissions",
                    "did i request anything",
                    "status of my orders",
                ],
                "user_profile": [
                    "my profile account details",
                    "about me my status",
                    "my account information",
                ],
                "allocate_resources": [
                    "allocate send resources",
                    "distribute dispatch resources",
                    "assign resources to zone",
                    "send supplies to location",
                ],
                "generate_report": [
                    "generate situation report",
                    "create sitrep",
                    "daily status report",
                    "generate report for disaster",
                ],
                "anomalies": [
                    "any anomaly alerts",
                    "unusual patterns detected",
                    "warning alerts active",
                    "irregularities in data",
                ],
                "users_overview": [
                    "how many users total",
                    "user count by role",
                    "registered accounts overview",
                    "platform user statistics",
                ],
            }

            # Pre-encode all exemplars
            exemplar_embeddings = {}
            for intent, phrases in intent_exemplars.items():
                exemplar_embeddings[intent] = model.encode(phrases, convert_to_tensor=True)

            _semantic_classifier = {
                "model": model,
                "exemplar_embeddings": exemplar_embeddings,
                "util": util,
            }
            logger.info("Semantic intent classifier loaded successfully")
        except Exception as exc:
            logger.warning("Failed to load semantic classifier: %s — falling back to regex", exc)
            _semantic_classifier = None
    return _semantic_classifier


# ── Endpoints ───────────────────────────────────────────────────────────────────


@router.post("/query", response_model=LLMQueryResponse)
async def llm_query(
    body: LLMQueryRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a query to DisasterGPT and receive a full response."""
    logger.info("LLM query from user=%s: %.80s...", user.get("id", "?"), body.query)

    try:
        rag = _get_rag()
        result = await rag.query(
            question=body.query,
            disaster_id=body.disaster_id,
            top_k=body.top_k,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
        )
        return LLMQueryResponse(
            response=result["response"],
            sources=[LLMSource(**s) for s in result["sources"]],
            confidence=result["confidence"],
            disaster_id=result.get("disaster_id"),
            documents_retrieved=result.get("documents_retrieved", 0),
        )
    except RuntimeError as exc:
        logger.error("LLM backend error: %s", exc)
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {exc}")
    except Exception as exc:
        logger.error("LLM query failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="LLM query failed")


@router.post("/stream")
async def llm_stream(
    body: LLMQueryRequest,
    user: dict = Depends(get_current_user),
):
    """Streaming version — returns server-sent events (SSE)."""
    logger.info("LLM stream from user=%s: %.80s...", user.get("id", "?"), body.query)

    async def event_generator():
        try:
            rag = _get_rag()
            async for chunk in rag.query_stream(
                question=body.query,
                disaster_id=body.disaster_id,
                top_k=body.top_k,
                max_tokens=body.max_tokens,
                temperature=body.temperature,
            ):
                yield f"data: {chunk}\n\n"
        except Exception as exc:
            logger.error("LLM stream error: %s", exc, exc_info=True)
            error_payload = json.dumps({"type": "error", "data": str(exc)})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/index", response_model=LLMIndexResponse)
async def llm_index(
    user: dict = Depends(require_role("admin")),
):
    """Re-index the knowledge base. Admin-only."""
    logger.info("Knowledge base re-index triggered by user=%s", user.get("id", "?"))

    try:
        rag = _get_rag()
        kb = rag.knowledge_base
        total_indexed = 0

        try:
            resp = await db.table("disasters").select("*").async_execute()
            if resp.data:
                count = kb.index_disasters_from_db(resp.data)
                total_indexed += count
        except Exception as exc:
            logger.warning("DB disaster indexing failed: %s", exc)

        from pathlib import Path

        reports_path = Path("training_data/disaster_instructions.jsonl")
        if reports_path.exists():
            count = kb.index_situation_reports(reports_path)
            total_indexed += count

        return LLMIndexResponse(
            indexed=total_indexed,
            total=kb.count,
            message=f"Indexed {total_indexed} documents. Total in knowledge base: {kb.count}",
        )
    except Exception as exc:
        logger.error("Indexing failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}")


@router.get("/stats", response_model=LLMStatsResponse)
async def llm_stats(
    user: dict = Depends(get_current_user),
):
    """Get knowledge base statistics."""
    try:
        rag = _get_rag()
        return LLMStatsResponse(total_documents=rag.knowledge_base.count, status="operational")
    except Exception as exc:
        logger.warning("Stats retrieval failed: %s", exc)
        return LLMStatsResponse(total_documents=0, status=f"degraded: {exc}")


# ── Enhanced Intent Classification ─────────────────────────────────────────────


_CAUSAL_PATTERNS = re.compile(
    r"\b(what.?if|counterfactual|causal|root.?cause|intervene|intervention|"
    r"would.?have|effect.?of|impact.?of.+on|treatment.?effect|"
    r"reduce.?casualties|reduce.?damage|why.?did|cause.?of|"
    r"explain.?why|explain.?priority|explain.?decision|"
    r"how.?did.?you|reasoning.?behind|justify|rationale)\b",
    re.IGNORECASE,
)

_MULTI_AGENT_PATTERNS = re.compile(
    r"\b(coordinate|deploy|allocate.?resource|emergency.?response|"
    r"multi.?agent|agents?|predict.?and.?allocate|triage|"
    r"prioriti[sz]e|dispatch|mobilize|action.?plan|response.?plan|"
    r"send.?team|resource.?distribution|volunteer.?deploy)\b",
    re.IGNORECASE,
)


def _classify_intent(query: str) -> str:
    """Classify query intent using semantic similarity (with regex fallback)."""
    # Try semantic classification first
    classifier = _get_semantic_classifier()
    if classifier:
        try:
            model = classifier["model"]
            exemplar_embeddings = classifier["exemplar_embeddings"]
            util = classifier["util"]
            import numpy as np

            query_embedding = model.encode(query, convert_to_tensor=True)

            best_intent = "general"
            best_score = 0.0

            for intent, embeddings in exemplar_embeddings.items():
                scores = util.cos_sim(query_embedding, embeddings)
                max_score = float(scores.max())
                if max_score > best_score:
                    best_score = max_score
                    best_intent = intent

            # Threshold: if similarity is too low, fall back to general
            if best_score >= 0.35:
                logger.info("Semantic intent: %s (score=%.3f)", best_intent, best_score)
                return best_intent
        except Exception as exc:
            logger.debug("Semantic classification failed: %s — using regex fallback", exc)

    # Regex fallback
    causal_score = len(_CAUSAL_PATTERNS.findall(query))
    agent_score = len(_MULTI_AGENT_PATTERNS.findall(query))

    if causal_score > 0 and causal_score >= agent_score:
        return "causal"
    if agent_score > 0:
        return "multi_agent"
    return _detect_intent_fallback(query)


def _detect_intent_fallback(message: str) -> str:
    """Detect intent category from user message using keyword matching."""
    msg = message.lower()

    if any(p in msg for p in ["my request", "my orders", "my submission", "did i request", "status of my", "track my"]):
        return "user_requests"
    if any(p in msg for p in ["my profile", "my account", "my details", "about me", "my status"]):
        return "user_profile"
    if any(p in msg for p in ["running low", "low stock", "shortage", "almost out", "depleted", "need more"]):
        return "low_stock"
    if any(p in msg for p in ["allocate", "send resources", "distribute resources", "dispatch resources", "assign resources"]):
        return "allocate_resources"
    if any(p in msg for p in ["generate report", "create report", "sitrep", "situation report", "status report", "daily report"]):
        return "generate_report"
    if any(p in msg for p in ["how many request", "number of request", "request count", "pending request", "open request", "total request"]):
        return "resource_requests"
    if any(p in msg for p in ["how many users", "number of users", "total users", "user count", "registered users", "all users", "list users", "user accounts", "total accounts"]):
        return "users_overview"
    if any(p in msg for p in ["what resources are available", "available resources", "inventory", "stock", "supply", "resources we have"]):
        return "available_resources"
    if any(p in msg for p in ["disaster status", "active disaster", "current disaster", "emergency status", "which disaster", "what disaster"]):
        return "disaster_status"
    if any(p in msg for p in ["anomal", "alert", "warning", "unusual", "irregularit"]):
        return "anomalies"
    if any(p in msg for p in ["briefing", "brief me", "daily brief", "admin brief", "morning brief", "what needs attention", "what should i know", "critical issues"]):
        return "briefing"
    if any(p in msg for p in ["resource gap", "supply gap", "demand gap", "deficit", "supply vs demand", "supply and demand", "what are we short on", "biggest gap", "coverage"]):
        return "supply_demand_gap"
    if any(p in msg for p in ["stale request", "stuck request", "old request", "pending too long", "overdue request", "how fast", "fulfillment time", "how long does it take", "lifecycle", "bottleneck"]):
        return "request_lifecycle"
    if any(p in msg for p in ["chatbot activity", "chatbot intake", "victim chatbot", "what are victims requesting", "chatbot abandon", "intake activity", "chatbot session"]):
        return "chatbot_activity"
    if any(p in msg for p in ["when do we get", "peak hour", "peak time", "busiest time", "busiest day", "request pattern", "activity pattern", "heatmap", "temporal"]):
        return "activity_heatmap"
    if any(p in msg for p in ["engag", "active user", "idle volunteer", "inactive", "who is active", "volunteer activity", "donor activity", "user activity"]):
        return "engagement"
    if any(p in msg for p in ["new user", "signup", "sign up", "registration", "who registered", "new account", "onboarding", "incomplete profile", "growth"]):
        return "registration_trends"
    if any(p in msg for p in ["pipeline", "funnel", "request journey", "completion rate", "rejection rate", "workflow", "request flow", "how many completed", "request status breakdown"]):
        return "request_pipeline"
    if any(p in msg for p in ["trend", "getting better", "getting worse", "week over week", "improving", "declining", "compared to last", "going up", "going down", "trajectory"]):
        return "trends"
    if any(p in msg for p in ["which area", "location", "where are request", "geographic", "region", "underserved", "which city", "which place", "spatial", "where should we"]):
        return "geographic"
    if any(p in msg for p in ["compare disaster", "disaster scorecard", "disaster performance", "which disaster is", "worst disaster", "best disaster", "health score", "disaster comparison"]):
        return "disaster_comparison"
    if any(p in msg for p in ["ngo performance", "volunteer performance", "responder", "who is fastest", "which ngo", "ngo completion", "best ngo", "worst ngo", "turnaround", "ngo workload"]):
        return "responder_performance"
    if any(p in msg for p in ["daily digest", "weekly digest", "full summary", "comprehensive report", "everything", "full report", "daily report", "weekly report", "complete overview"]):
        return "digest"
    return "general"


# ── Follow-Up Suggestion Generator ─────────────────────────────────────────────


def _generate_follow_up_suggestions(intent: str, context_data: dict | None, user_role: str) -> list[str]:
    """Generate contextual follow-up question suggestions based on intent and context."""
    suggestions_map = {
        "briefing": [
            "Tell me more about the stale requests",
            "Which disasters need immediate attention?",
            "Show me the supply-demand gaps",
        ],
        "supply_demand_gap": [
            "Which resource type has the worst deficit?",
            "Can you allocate resources to fix the gaps?",
            "Show me who can fulfill these shortages",
        ],
        "request_lifecycle": [
            "Which priority level is slowest?",
            "Show me the stale requests in detail",
            "Compare fulfillment across disasters",
        ],
        "trends": [
            "Why is this metric declining?",
            "Show me the geographic breakdown",
            "Compare performance scorecards",
        ],
        "geographic": [
            "Which underserved area needs help most?",
            "Show me resources available near these locations",
            "Allocate resources to underserved areas",
        ],
        "disaster_comparison": [
            "What's causing the worst disaster's low health score?",
            "Show me responder performance for each disaster",
            "Generate a situation report for the worst disaster",
        ],
        "responder_performance": [
            "Which NGO has the best turnaround time?",
            "Show me overloaded responders",
            "How can we improve completion rates?",
        ],
        "digest": [
            "Drill down into the trends section",
            "Show me the supply-demand gaps in detail",
            "Give me a briefing on what needs attention now",
        ],
        "resource_requests": [
            "Show me only critical priority requests",
            "Which resource type has most requests?",
            "How many requests are stale?",
        ],
        "available_resources": [
            "Which resources are running low?",
            "Show me supply vs demand gaps",
            "Where should we reallocate from?",
        ],
        "disaster_status": [
            "Compare disaster scorecards",
            "Show me resources for the worst disaster",
            "Generate a situation report",
        ],
        "low_stock": [
            "Which locations have these items?",
            "Show me supply-demand gaps",
            "Can you help me allocate more resources?",
        ],
        "chatbot_activity": [
            "What are victims requesting most?",
            "Why is the abandonment rate high?",
            "Show me priority distribution",
        ],
        "activity_heatmap": [
            "What causes the peak hours?",
            "Show me trends over time",
            "Compare this week vs last week",
        ],
        "engagement": [
            "How can we increase volunteer activity?",
            "Show me registration trends",
            "Which role has lowest engagement?",
        ],
        "registration_trends": [
            "How can we reduce incomplete profiles?",
            "Show me user engagement",
            "What's the growth trajectory?",
        ],
        "request_pipeline": [
            "Where are requests getting stuck?",
            "Show me the bottleneck",
            "Compare pipeline by priority",
        ],
        "anomalies": [
            "Give me details on the critical alerts",
            "Show me the affected resources",
            "What's the recommended action?",
        ],
    }

    # Role-specific suggestions
    role_suggestions = {
        "admin": [
            "Give me a comprehensive daily digest",
            "Show me what needs attention right now",
            "Compare disaster performance scorecards",
        ],
        "coordinator": [
            "Where should we deploy resources?",
            "Show me responder performance",
            "Which area is most underserved?",
        ],
        "ngo": [
            "Show me my assigned requests",
            "What's our current inventory status?",
            "Which requests are highest priority?",
        ],
        "victim": [
            "What's the status of my requests?",
            "What resources are available near me?",
            "How do I request help?",
        ],
    }

    suggestions = suggestions_map.get(intent, [])

    # Add role-specific suggestions if we don't have enough
    if len(suggestions) < 3 and user_role in role_suggestions:
        for s in role_suggestions[user_role]:
            if s not in suggestions:
                suggestions.append(s)
            if len(suggestions) >= 3:
                break

    return suggestions[:3]


# ── Action Card Generator ──────────────────────────────────────────────────────


def _generate_action_cards(intent: str, context_data: dict | None, user_role: str) -> list[dict]:
    """Generate actionable cards based on the response context."""
    cards = []

    # Only generate action cards for elevated roles
    if user_role not in ("admin", "coordinator", "super_admin"):
        return cards

    if intent == "supply_demand_gap" and context_data:
        gaps = context_data.get("data", {}).get("critical_shortages", [])
        for gap in gaps[:3]:
            cards.append({
                "type": "allocate_resources",
                "title": f"Allocate {gap.get('type', 'resources')}",
                "description": f"Only {gap.get('coverage_pct', 0)}% coverage — {gap.get('demand', 0)} units demanded, {gap.get('supply', 0)} available",
                "action": {
                    "endpoint": "/api/resources/allocate",
                    "method": "POST",
                    "payload": {
                        "resource_type": gap.get("type"),
                        "quantity_needed": gap.get("demand", 0) - gap.get("supply", 0),
                    },
                },
                "confirm_label": "Allocate Now",
                "style": "destructive",
            })

    elif intent == "briefing" and context_data:
        alert_count = context_data.get("alert_count", 0)
        if alert_count > 0:
            cards.append({
                "type": "view_alerts",
                "title": f"View {alert_count} Active Alerts",
                "description": "There are items requiring your immediate attention",
                "action": {
                    "endpoint": "/api/llm/chat",
                    "method": "POST",
                    "payload": {"message": "Show me the active alerts in detail"},
                },
                "confirm_label": "View Alerts",
                "style": "warning",
            })

    elif intent == "generate_report":
        cards.append({
            "type": "generate_sitrep",
            "title": "Generate Situation Report",
            "description": "Create a formal SITREP document from current data",
            "action": {
                "endpoint": "/api/nlp/sitrep/generate",
                "method": "POST",
                "payload": {},
            },
            "confirm_label": "Generate Report",
            "style": "primary",
        })

    elif intent == "disaster_comparison" and context_data:
        scorecards = context_data.get("data", [])
        if scorecards:
            worst = scorecards[0]
            if worst.get("health_score", 10) <= 5:
                cards.append({
                    "type": "allocate_to_disaster",
                    "title": f"Boost Resources for {worst.get('title', 'Disaster')}",
                    "description": f"Health score: {worst['health_score']}/10, {worst.get('pending', 0)} pending requests",
                    "action": {
                        "endpoint": "/api/resources/allocate",
                        "method": "POST",
                        "payload": {"disaster_id": worst.get("disaster_id")},
                    },
                    "confirm_label": "Allocate Resources",
                    "style": "destructive",
                })

    elif intent == "request_lifecycle" and context_data:
        lifecycle = context_data.get("data", {})
        stale_count = lifecycle.get("stale_count", 0)
        if stale_count > 0:
            cards.append({
                "type": "review_stale",
                "title": f"Review {stale_count} Stale Requests",
                "description": "Requests pending > 48 hours need attention",
                "action": {
                    "endpoint": "/api/llm/chat",
                    "method": "POST",
                    "payload": {"message": "Show me the stale requests in detail and suggest actions"},
                },
                "confirm_label": "Review Stale",
                "style": "warning",
            })

    return cards[:3]  # Max 3 action cards


# ── Conversation Memory with Summarization ─────────────────────────────────────


async def _summarize_conversation(messages: list[dict], max_summary_tokens: int = 200) -> str:
    """Use the LLM to summarize older conversation messages into a compact prefix."""
    if len(messages) <= 4:
        return ""

    # Take messages older than the last 4
    older_messages = messages[:-4]
    conversation_text = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')[:300]}" for m in older_messages
    )

    try:
        from groq import Groq

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            return ""

        client = Groq(api_key=api_key)
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarize the following conversation in 2-3 sentences. "
                            "Focus on key topics discussed, decisions made, and any data mentioned. "
                            "Be concise and factual."
                        ),
                    },
                    {"role": "user", "content": conversation_text},
                ],
                max_tokens=max_summary_tokens,
                temperature=0.3,
            ),
        )
        summary = (response.choices[0].message.content or "").strip()
        return summary
    except Exception as exc:
        logger.debug("Conversation summarization failed: %s", exc)
        return ""


# ── Context Pruning by Intent ──────────────────────────────────────────────────

# Map intents to the context keys they need
_INTENT_CONTEXT_MAP = {
    "resource_requests": ["resource_requests_summary", "global_resource_requests"],
    "available_resources": ["inventory_summary"],
    "disaster_status": ["active_disasters", "focused_disaster"],
    "low_stock": ["inventory_summary"],
    "briefing": [
        "active_disasters", "resource_requests_summary", "inventory_summary",
        "active_alerts", "request_lifecycle", "supply_demand_gaps",
    ],
    "supply_demand_gap": ["supply_demand_gaps", "inventory_summary"],
    "request_lifecycle": ["request_lifecycle"],
    "chatbot_activity": ["chatbot_intake_activity"],
    "activity_heatmap": ["activity_heatmap"],
    "engagement": ["engagement_summary", "platform_users"],
    "registration_trends": ["registration_insights", "platform_users"],
    "request_pipeline": ["request_pipeline"],
    "trends": ["trend_analysis"],
    "geographic": ["geographic_insights"],
    "disaster_comparison": ["disaster_scorecards"],
    "responder_performance": ["responder_performance"],
    "digest": None,  # Keep all context
    "user_requests": ["user_requests"],
    "user_profile": ["current_user"],
    "allocate_resources": ["active_disasters", "supply_demand_gaps", "inventory_summary"],
    "generate_report": ["active_disasters", "resource_requests_summary", "inventory_summary", "active_alerts"],
    "anomalies": ["active_alerts"],
    "users_overview": ["platform_users"],
    "general": None,  # Keep all context for general queries
    "causal": ["active_disasters"],
    "multi_agent": ["active_disasters", "supply_demand_gaps"],
}


def _prune_context_by_intent(context: dict, intent: str) -> dict:
    """Prune context to only include data relevant to the detected intent."""
    allowed_keys = _INTENT_CONTEXT_MAP.get(intent)

    # None means keep everything
    if allowed_keys is None:
        return context

    # Always include these baseline keys
    always_include = {"current_user", "focused_disaster"}

    pruned = {}
    for key in set(allowed_keys) | always_include:
        if key in context:
            pruned[key] = context[key]

    return pruned


# ── Session Persistence (DB-backed) ────────────────────────────────────────────


async def _persist_session(session_id: str, user: dict) -> None:
    """Create or update a session record in the database."""
    try:
        user_id = user.get("id", "unknown")
        user_role = user.get("role", "unknown")
        user_name = user.get("name", "unknown")

        # Upsert session
        existing = (
            await db_admin.table("disastergpt_sessions")
            .select("session_id")
            .eq("session_id", session_id)
            .maybe_single()
            .async_execute()
        )

        if existing.data:
            await db_admin.table("disastergpt_sessions").update({
                "updated_at": datetime.now(UTC).isoformat(),
                "last_message_at": datetime.now(UTC).isoformat(),
            }).eq("session_id", session_id).async_execute()
        else:
            await db_admin.table("disastergpt_sessions").insert({
                "session_id": session_id,
                "user_id": user_id,
                "user_role": user_role,
                "user_name": user_name,
                "message_count": 0,
            }).async_execute()
    except Exception as exc:
        logger.warning("Failed to persist session %s: %s", session_id, exc)


async def _persist_message(
    session_id: str,
    role: str,
    content: str,
    intent: str | None = None,
    context_data: dict | None = None,
    follow_up_suggestions: list[str] | None = None,
    action_cards: list[dict] | None = None,
) -> None:
    """Persist a message to the database."""
    try:
        await db_admin.table("disastergpt_messages").insert({
            "session_id": session_id,
            "role": role,
            "content": content,
            "intent": intent,
            "context_data": context_data,
            "follow_up_suggestions": follow_up_suggestions,
            "action_cards": action_cards,
        }).async_execute()

        # Update session message count
        await db_admin.table("disastergpt_sessions").update({
            "last_message_at": datetime.now(UTC).isoformat(),
            "message_count": db_admin.rpc("increment", {"x": 1}),  # May need manual SQL
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("session_id", session_id).async_execute()
    except Exception as exc:
        logger.warning("Failed to persist message for session %s: %s", session_id, exc)


async def _get_session_history_from_db(session_id: str, limit: int = 20) -> list[dict]:
    """Retrieve message history from the database."""
    try:
        resp = (
            await db_admin.table("disastergpt_messages")
            .select("role, content, intent, created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .limit(limit)
            .async_execute()
        )
        return [
            {
                "role": m.get("role", "user"),
                "content": m.get("content", ""),
                "intent": m.get("intent"),
                "timestamp": m.get("created_at", ""),
            }
            for m in (resp.data or [])
        ]
    except Exception as exc:
        logger.warning("Failed to load session history from DB: %s", exc)
        return []


async def _get_conversation_summary_from_db(session_id: str) -> str:
    """Get the stored conversation summary for a session."""
    try:
        resp = (
            await db_admin.table("disastergpt_sessions")
            .select("conversation_summary")
            .eq("session_id", session_id)
            .maybe_single()
            .async_execute()
        )
        if resp.data:
            return resp.data.get("conversation_summary") or ""
    except Exception:
        pass
    return ""


async def _update_conversation_summary(session_id: str, messages: list[dict]) -> None:
    """Generate and store a conversation summary if there are enough messages."""
    if len(messages) < 6:
        return

    summary = await _summarize_conversation(messages)
    if summary:
        try:
            await db_admin.table("disastergpt_sessions").update({
                "conversation_summary": summary,
            }).eq("session_id", session_id).async_execute()
        except Exception as exc:
            logger.warning("Failed to update conversation summary: %s", exc)


# ── In-memory fallback (kept for backward compat) ──────────────────────────────

MAX_HISTORY = 10

_chat_sessions: dict[str, dict] = {}


def _get_or_create_session(session_id: str | None) -> tuple[str, dict]:
    """Get existing session or create new one (in-memory fallback)."""
    if session_id and session_id in _chat_sessions:
        return session_id, _chat_sessions[session_id]

    new_id = session_id or str(uuid.uuid4())
    _chat_sessions[new_id] = {
        "messages": [],
        "created_at": datetime.now(UTC).isoformat(),
    }
    return new_id, _chat_sessions[new_id]


def _add_message_to_session(session_id: str, role: str, content: str) -> None:
    """Add a message to session history (in-memory fallback)."""
    if session_id not in _chat_sessions:
        _chat_sessions[session_id] = {
            "messages": [],
            "created_at": datetime.now(UTC).isoformat(),
        }

    session = _chat_sessions[session_id]
    session["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(UTC).isoformat(),
    })

    if len(session["messages"]) > MAX_HISTORY:
        session["messages"] = session["messages"][-MAX_HISTORY:]


# ── Context Pulling Functions ───────────────────────────────────────────────────


async def _get_active_disasters(limit: int = 10) -> list[dict]:
    """Get active disasters ordered by most recent."""
    try:
        resp = await db.table("disasters").select(
            "id,title,type,severity,status,affected_population,casualties,created_at"
        ).eq("status", "active").order("created_at", desc=True).limit(limit).async_execute()
        return resp.data or []
    except Exception as e:
        logger.warning(f"Failed to fetch active disasters: {e}")
        return []


async def _get_resource_requests_summary() -> dict:
    """Get resource request summary from live Supabase data."""
    try:
        yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()

        total_resp = await db_admin.table("resource_requests").select("id", count="exact").limit(1).async_execute()
        total_all_time = int(total_resp.count or 0)

        recent_resp = (
            await db_admin.table("resource_requests")
            .select("id,status,resource_type,priority,created_at")
            .gte("created_at", yesterday)
            .async_execute()
        )
        recent_requests = recent_resp.data or []

        by_status: dict[str, int] = {}
        for status in ["pending", "approved", "assigned", "in_progress", "completed", "rejected"]:
            status_resp = (
                await db_admin.table("resource_requests")
                .select("id", count="exact")
                .eq("status", status)
                .limit(1)
                .async_execute()
            )
            by_status[status] = int(status_resp.count or 0)

        by_type: dict[str, int] = defaultdict(int)
        for req in recent_requests:
            req_type = req.get("resource_type", "unknown")
            by_type[str(req_type)] += 1

        return {
            "total": total_all_time,
            "by_status": by_status,
            "by_type": dict(by_type),
            "recent_24h_total": len(recent_requests),
            "time_range": "last 24h",
        }
    except Exception as e:
        logger.warning(f"Failed to fetch resource requests summary: {e}")
        return {"total": 0, "by_status": {}, "by_type": {}, "recent_24h_total": 0, "time_range": "last 24h"}


async def _get_global_resource_requests(limit: int = 300) -> list[dict]:
    """Get recent individual resource requests across all users."""
    try:
        rows_resp = (
            await db_admin.table("resource_requests")
            .select(
                "id,victim_id,resource_type,quantity,priority,status,description,address_text,assigned_to,created_at"
            )
            .order("created_at", desc=True)
            .limit(min(max(limit, 1), 1000))
            .async_execute()
        )
        rows = rows_resp.data or []

        if not rows:
            return []

        victim_ids = {str(r.get("victim_id")) for r in rows if r.get("victim_id")}
        users_map: dict[str, dict] = {}
        if victim_ids:
            users_resp = (
                await db_admin.table("users")
                .select("id,full_name,email,role")
                .in_("id", list(victim_ids))
                .async_execute()
            )
            users = users_resp.data or []
            users_map = {str(u.get("id")): u for u in users if u.get("id")}

        enriched = []
        for req in rows:
            victim = users_map.get(str(req.get("victim_id")), {})
            enriched.append({
                **req,
                "victim_name": victim.get("full_name"),
                "victim_email": victim.get("email"),
                "victim_role": victim.get("role"),
            })
        return enriched
    except Exception as e:
        logger.warning(f"Failed to fetch global individual resource requests: {e}")
        return []


async def _get_inventory_summary() -> dict:
    """Get current resource inventory summary."""
    resources = []
    try:
        resp = await db.table("resources").select(
            "id,type,quantity,status"
        ).eq("status", "available").async_execute()
        for item in (resp.data or []):
            item["resource_type"] = item.pop("type", "unknown")
        resources = resp.data or []
    except Exception as e:
        logger.warning(f"Failed to fetch inventory: {e}")
        return {"total_resources": 0, "by_type": {}, "low_stock": []}

    by_type: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_quantity": 0})
    for res in resources:
        res_type = res.get("resource_type", "unknown")
        qty = res.get("quantity", 0) or 0
        by_type[res_type]["count"] += 1
        by_type[res_type]["total_quantity"] += qty

    low_stock = [k for k, v in by_type.items() if v["total_quantity"] < 50]

    return {
        "total_resources": len(resources),
        "by_type": dict(by_type),
        "low_stock": low_stock,
    }


async def _get_active_alerts() -> list[dict]:
    """Get active anomaly alerts."""
    try:
        resp = await db.table("anomaly_alerts").select(
            "id,alert_type,severity,description,status,created_at"
        ).eq("status", "active").order("severity", desc=True).limit(10).async_execute()
        return resp.data or []
    except Exception as e:
        logger.warning(f"Failed to fetch active alerts: {e}")
        return []


async def _get_chatbot_intake_activity(hours: int = 24) -> dict:
    """Get recent victim chatbot intake activity."""
    try:
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        resp = await db_admin.table("chatbot_sessions").select(
            "id,session_id,final_resource_type,final_priority,completion_status,created_at"
        ).gte("created_at", cutoff).order("created_at", desc=True).limit(100).async_execute()

        sessions = resp.data or []
        completed = [s for s in sessions if s.get("completion_status") == "completed"]
        abandoned = [s for s in sessions if s.get("completion_status") == "abandoned"]

        resource_demand: dict[str, int] = {}
        priority_dist: dict[str, int] = {}
        for s in completed:
            rt = s.get("final_resource_type")
            if rt:
                resource_demand[rt] = resource_demand.get(rt, 0) + 1
            pri = s.get("final_priority")
            if pri:
                priority_dist[pri] = priority_dist.get(pri, 0) + 1

        return {
            "total_sessions": len(sessions),
            "completed": len(completed),
            "abandoned": len(abandoned),
            "abandonment_rate": round(len(abandoned) / max(len(sessions), 1) * 100, 1),
            "resource_demand": resource_demand,
            "priority_distribution": priority_dist,
            "time_range_hours": hours,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch chatbot intake activity: {e}")
        return {}


async def _get_request_lifecycle_metrics() -> dict:
    """Compute request processing speed and stale request metrics."""
    try:
        resp = await db_admin.table("resource_requests").select(
            "id,status,priority,resource_type,created_at,updated_at"
        ).in_("status", ["completed", "delivered"]).order(
            "updated_at", desc=True
        ).limit(200).async_execute()

        completed = resp.data or []
        durations: list[float] = []
        by_priority: dict[str, list[float]] = {}
        for req in completed:
            created = req.get("created_at")
            updated = req.get("updated_at")
            if created and updated:
                from datetime import datetime as _dt
                try:
                    c = _dt.fromisoformat(created.replace("Z", "+00:00"))
                    u = _dt.fromisoformat(updated.replace("Z", "+00:00"))
                    hours = (u - c).total_seconds() / 3600
                    if hours >= 0:
                        durations.append(hours)
                        pri = req.get("priority", "medium")
                        by_priority.setdefault(pri, []).append(hours)
                except (ValueError, TypeError):
                    pass

        result: dict = {"sample_size": len(durations)}
        if durations:
            durations.sort()
            result["median_fulfillment_hours"] = round(durations[len(durations) // 2], 1)
            result["avg_fulfillment_hours"] = round(sum(durations) / len(durations), 1)
            result["by_priority"] = {
                k: round(sum(v) / len(v), 1) for k, v in by_priority.items()
            }

        pending_resp = await db_admin.table("resource_requests").select(
            "id,created_at,priority"
        ).eq("status", "pending").async_execute()

        stale_requests: list[dict] = []
        now = datetime.now(UTC)
        for p in (pending_resp.data or []):
            created = p.get("created_at")
            if created:
                from datetime import datetime as _dt
                try:
                    c = _dt.fromisoformat(created.replace("Z", "+00:00"))
                    age_hours = (now - c).total_seconds() / 3600
                    if age_hours > 48:
                        stale_requests.append({
                            "id": p["id"],
                            "age_hours": round(age_hours, 1),
                            "priority": p.get("priority"),
                        })
                except (ValueError, TypeError):
                    pass

        result["stale_pending_requests"] = stale_requests[:10]
        result["stale_count"] = len(stale_requests)
        return result
    except Exception as e:
        logger.warning(f"Request lifecycle metrics failed: {e}")
        return {}


async def _get_activity_heatmap(days: int = 7) -> dict:
    """Aggregate request creation times into hourly/daily buckets."""
    try:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        resp = await db_admin.table("resource_requests").select(
            "created_at"
        ).gte("created_at", cutoff).async_execute()

        rows = resp.data or []
        hourly: dict[int, int] = {h: 0 for h in range(24)}
        daily: dict[str, int] = {}

        for r in rows:
            ca = r.get("created_at")
            if not ca:
                continue
            from datetime import datetime as _dt
            try:
                dt = _dt.fromisoformat(ca.replace("Z", "+00:00"))
                hourly[dt.hour] = hourly.get(dt.hour, 0) + 1
                day_key = dt.strftime("%A")
                daily[day_key] = daily.get(day_key, 0) + 1
            except (ValueError, TypeError):
                pass

        peak_hour = max(hourly, key=lambda k: hourly[k]) if rows else None
        peak_day = max(daily, key=lambda k: daily[k]) if daily else None

        return {
            "hourly_distribution": hourly,
            "daily_distribution": daily,
            "peak_hour": peak_hour,
            "peak_day": peak_day,
            "total_requests": len(rows),
            "days_analyzed": days,
        }
    except Exception as e:
        logger.warning(f"Activity heatmap failed: {e}")
        return {}


async def _get_supply_demand_gap() -> dict:
    """Compare pending demand against donor/NGO supply by resource type.
    
    New model: Victims create demands, donors/NGOs supply directly via pledges and availability.
    """
    try:
        # Get demand from pending requests
        demand_resp = await db_admin.table("resource_requests").select(
            "resource_type,quantity"
        ).in_("status", ["pending", "approved", "assigned"]).async_execute()

        demand_by_type: dict[str, int] = {}
        for r in (demand_resp.data or []):
            rt = r.get("resource_type", "unknown")
            qty = r.get("quantity", 1) or 1
            demand_by_type[rt] = demand_by_type.get(rt, 0) + qty

        # Get supply from donor pledges (committed resources)
        supply_by_type: dict[str, int] = {}
        try:
            # Check donor_pledges for committed supply
            pledge_resp = await db_admin.table("donor_pledges").select(
                "resource_type,quantity_pledged,status"
            ).in_("status", ["pending", "confirmed"]).async_execute()
            for r in (pledge_resp.data or []):
                rt = r.get("resource_type", "unknown")
                qty = r.get("quantity_pledged", 0) or 0
                supply_by_type[rt] = supply_by_type.get(rt, 0) + qty
        except Exception as e:
            logger.debug(f"Failed to fetch donor pledges: {e}")

        try:
            # Also check available_resources for NGO/donor inventory
            avail_resp = await db_admin.table("available_resources").select(
                "resource_type,total_quantity,claimed_quantity,is_active"
            ).eq("is_active", True).async_execute()
            for r in (avail_resp.data or []):
                rt = r.get("resource_type", "unknown")
                total = r.get("total_quantity", 0) or 0
                claimed = r.get("claimed_quantity", 0) or 0
                available = total - claimed
                if available > 0:
                    supply_by_type[rt] = supply_by_type.get(rt, 0) + available
        except Exception as e:
            logger.debug(f"Failed to fetch available resources: {e}")

        # Calculate fulfilled supply from completed requests
        try:
            fulfilled_resp = await db_admin.table("resource_requests").select(
                "resource_type,quantity"
            ).in_("status", ["completed", "delivered"]).async_execute()
            for r in (fulfilled_resp.data or []):
                rt = r.get("resource_type", "unknown")
                qty = r.get("quantity", 0) or 0
                # Add fulfilled to supply (represents capacity that has been delivered)
                supply_by_type[rt] = supply_by_type.get(rt, 0) + qty
        except Exception as e:
            logger.debug(f"Failed to fetch fulfilled requests: {e}")

        all_types = set(demand_by_type) | set(supply_by_type)
        gaps = []
        for rt in sorted(all_types):
            demand = demand_by_type.get(rt, 0)
            supply = supply_by_type.get(rt, 0)
            gap = supply - demand
            coverage = round(supply / max(demand, 1) * 100, 1)
            gaps.append({
                "type": rt,
                "demand": demand,
                "supply": supply,
                "gap": gap,
                "coverage_pct": coverage,
                "status": "surplus" if gap > 0 else "deficit" if gap < 0 else "matched",
            })

        gaps.sort(key=lambda g: g["gap"])
        critical_shortages = [g for g in gaps if g["coverage_pct"] < 50 and g["demand"] > 0]

        return {
            "gaps": gaps,
            "critical_shortages": critical_shortages,
            "total_demand": sum(demand_by_type.values()),
            "total_supply": sum(supply_by_type.values()),
            "model": "victim_demand_donor_supply",
        }
    except Exception as e:
        logger.warning(f"Supply-demand gap analysis failed: {e}")
        return {"gaps": [], "critical_shortages": [], "total_demand": 0, "total_supply": 0, "model": "victim_demand_donor_supply"}


async def _get_engagement_summary() -> dict:
    """Summarize user engagement across roles."""
    try:
        cutoff_7d = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        cutoff_30d = (datetime.now(UTC) - timedelta(days=30)).isoformat()

        victim_resp = await db_admin.table("resource_requests").select(
            "victim_id"
        ).gte("created_at", cutoff_7d).async_execute()
        active_victims = len(set(
            r["victim_id"] for r in (victim_resp.data or []) if r.get("victim_id")
        ))

        active_volunteers = 0
        try:
            vol_resp = await db_admin.table("volunteer_assignments").select(
                "volunteer_id"
            ).gte("assigned_at", cutoff_30d).async_execute()
            active_volunteers = len(set(
                r["volunteer_id"] for r in (vol_resp.data or []) if r.get("volunteer_id")
            ))
        except Exception:
            pass

        active_donors = 0
        try:
            donor_resp = await db_admin.table("donations").select(
                "user_id"
            ).gte("created_at", cutoff_30d).async_execute()
            active_donors = len(set(
                r["user_id"] for r in (donor_resp.data or []) if r.get("user_id")
            ))
        except Exception:
            pass

        return {
            "active_victims_7d": active_victims,
            "active_volunteers_30d": active_volunteers,
            "active_donors_30d": active_donors,
        }
    except Exception as e:
        logger.warning(f"Engagement summary failed: {e}")
        return {}


async def _get_user_registration_insights() -> dict:
    """Track user registration trends."""
    try:
        cutoff_7d = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        cutoff_30d = (datetime.now(UTC) - timedelta(days=30)).isoformat()

        week_resp = await db_admin.table("users").select(
            "id,role,created_at"
        ).gte("created_at", cutoff_7d).async_execute()
        new_this_week = week_resp.data or []

        month_resp = await db_admin.table("users").select(
            "id,role,created_at"
        ).gte("created_at", cutoff_30d).async_execute()
        new_this_month = month_resp.data or []

        week_by_role: dict[str, int] = {}
        for u in new_this_week:
            role = u.get("role", "unknown") or "unknown"
            week_by_role[role] = week_by_role.get(role, 0) + 1

        month_by_role: dict[str, int] = {}
        for u in new_this_month:
            role = u.get("role", "unknown") or "unknown"
            month_by_role[role] = month_by_role.get(role, 0) + 1

        incomplete_resp = await db_admin.table("users").select(
            "id", count="exact"
        ).eq("is_profile_completed", False).limit(1).async_execute()
        incomplete_profiles = int(incomplete_resp.count or 0)

        return {
            "new_users_7d": len(new_this_week),
            "new_users_30d": len(new_this_month),
            "week_by_role": week_by_role,
            "month_by_role": month_by_role,
            "incomplete_profiles": incomplete_profiles,
        }
    except Exception as e:
        logger.warning(f"User registration insights failed: {e}")
        return {}


async def _get_request_pipeline_funnel() -> dict:
    """Show request journey funnel."""
    try:
        resp = await db_admin.table("resource_requests").select(
            "id,status,priority,resource_type,created_at"
        ).async_execute()
        rows = resp.data or []

        if not rows:
            return {"total": 0, "funnel": {}, "by_priority": {}}

        funnel: dict[str, int] = {}
        by_priority: dict[str, dict[str, int]] = {}
        for r in rows:
            status = r.get("status", "unknown")
            priority = r.get("priority", "medium")
            funnel[status] = funnel.get(status, 0) + 1
            if priority not in by_priority:
                by_priority[priority] = {}
            by_priority[priority][status] = by_priority[priority].get(status, 0) + 1

        total = len(rows)
        completed = funnel.get("completed", 0) + funnel.get("delivered", 0)
        rejected = funnel.get("rejected", 0)
        in_progress = funnel.get("in_progress", 0)
        assigned = funnel.get("assigned", 0)
        pending = funnel.get("pending", 0)

        completion_rate = round(completed / max(total, 1) * 100, 1)
        rejection_rate = round(rejected / max(total, 1) * 100, 1)
        active_pct = round((in_progress + assigned) / max(total, 1) * 100, 1)

        return {
            "total": total,
            "funnel": funnel,
            "by_priority": by_priority,
            "completion_rate": completion_rate,
            "rejection_rate": rejection_rate,
            "active_processing_pct": active_pct,
            "pending_count": pending,
            "completed_count": completed,
        }
    except Exception as e:
        logger.warning(f"Request pipeline funnel failed: {e}")
        return {}


async def _get_trend_analysis() -> dict:
    """Compare current week metrics against previous week."""
    try:
        now = datetime.now(UTC)
        tw_start = (now - timedelta(days=7)).isoformat()
        lw_start = (now - timedelta(days=14)).isoformat()

        results = await asyncio.gather(
            db_admin.table("resource_requests").select("id", count="exact").gte("created_at", tw_start).limit(1).async_execute(),
            db_admin.table("resource_requests").select("id", count="exact").gte("created_at", lw_start).lt("created_at", tw_start).limit(1).async_execute(),
            db_admin.table("users").select("id", count="exact").gte("created_at", tw_start).limit(1).async_execute(),
            db_admin.table("users").select("id", count="exact").gte("created_at", lw_start).lt("created_at", tw_start).limit(1).async_execute(),
            db_admin.table("resource_requests").select("id", count="exact").gte("updated_at", tw_start).in_("status", ["completed", "delivered"]).limit(1).async_execute(),
            db_admin.table("resource_requests").select("id", count="exact").gte("updated_at", lw_start).lt("updated_at", tw_start).in_("status", ["completed", "delivered"]).limit(1).async_execute(),
            return_exceptions=True,
        )

        def _safe_count(r, idx):
            v = results[idx]
            return int(v.count or 0) if not isinstance(v, Exception) else 0

        def _trend(cur: int, prev: int) -> dict:
            chg = cur - prev
            pct = round(chg / max(prev, 1) * 100, 1)
            return {"this_week": cur, "last_week": prev, "change": chg, "change_pct": pct,
                    "trend": "↑" if chg > 0 else ("↓" if chg < 0 else "→")}

        return {
            "request_volume": _trend(_safe_count(results, 0), _safe_count(results, 1)),
            "user_signups": _trend(_safe_count(results, 2), _safe_count(results, 3)),
            "completions": _trend(_safe_count(results, 4), _safe_count(results, 5)),
        }
    except Exception as e:
        logger.warning(f"Trend analysis failed: {e}")
        return {}


async def _get_geographic_insights() -> dict:
    """Aggregate requests and disasters by location."""
    try:
        req_resp = await db_admin.table("resource_requests").select(
            "address_text,status,priority"
        ).limit(500).async_execute()

        location_stats: dict[str, dict] = {}
        for r in (req_resp.data or []):
            addr = str(r.get("address_text") or "").strip()
            if not addr:
                continue
            loc_key = addr.split(",")[0].strip() if "," in addr else addr
            if loc_key not in location_stats:
                location_stats[loc_key] = {"total": 0, "pending": 0, "completed": 0, "high_priority": 0}
            location_stats[loc_key]["total"] += 1
            status = r.get("status", "")
            if status == "pending":
                location_stats[loc_key]["pending"] += 1
            elif status in ("completed", "delivered"):
                location_stats[loc_key]["completed"] += 1
            if r.get("priority") in ("critical", "high"):
                location_stats[loc_key]["high_priority"] += 1

        sorted_locs = sorted(location_stats.items(), key=lambda x: x[1]["total"], reverse=True)

        disaster_resp = await db_admin.table("disasters").select(
            "location,title,severity,status"
        ).eq("status", "active").async_execute()
        disaster_locations = [
            {"location": d.get("location"), "disaster": d.get("title", "Unknown"), "severity": d.get("severity")}
            for d in (disaster_resp.data or []) if d.get("location")
        ]

        resource_resp = await db_admin.table("resources").select(
            "name,type,quantity"
        ).eq("status", "available").limit(500).async_execute()
        resource_locs: dict[str, int] = {}
        for r in (resource_resp.data or []):
            rtype = str(r.get("type") or "unknown").strip()
            if rtype:
                resource_locs[rtype] = resource_locs.get(rtype, 0) + (r.get("quantity", 0) or 0)

        underserved = []
        for loc, stats in sorted_locs[:20]:
            res_avail = resource_locs.get(loc, 0)
            if stats["pending"] > 0 and res_avail < stats["total"]:
                underserved.append({"location": loc, "pending_requests": stats["pending"],
                                    "available_resources": res_avail, "high_priority": stats["high_priority"]})

        return {
            "top_locations": [{"location": loc, **stats} for loc, stats in sorted_locs[:15]],
            "disaster_locations": disaster_locations,
            "resource_coverage": dict(sorted(resource_locs.items(), key=lambda x: x[1], reverse=True)[:15]),
            "underserved_areas": underserved[:10],
            "total_locations": len(location_stats),
        }
    except Exception as e:
        logger.warning(f"Geographic insights failed: {e}")
        return {}


async def _get_disaster_scorecards() -> list[dict]:
    """Generate performance scorecards for each active disaster."""
    try:
        disasters_resp = await db_admin.table("disasters").select(
            "id,title,type,severity,status,affected_population,casualties,created_at"
        ).eq("status", "active").async_execute()
        disasters = disasters_resp.data or []
        if not disasters:
            return []

        scorecards = []
        for d in disasters:
            did = d.get("id")
            if not did:
                continue
            req_resp = await db_admin.table("resource_requests").select(
                "id,status,priority,created_at,updated_at"
            ).eq("disaster_id", did).async_execute()
            reqs = req_resp.data or []
            total_reqs = len(reqs)
            completed = sum(1 for r in reqs if r.get("status") in ("completed", "delivered"))
            pending = sum(1 for r in reqs if r.get("status") == "pending")
            in_prog = sum(1 for r in reqs if r.get("status") in ("assigned", "in_progress"))
            comp_rate = round(completed / max(total_reqs, 1) * 100, 1)

            durations = []
            for r in reqs:
                if r.get("status") in ("completed", "delivered") and r.get("created_at") and r.get("updated_at"):
                    try:
                        c = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                        u = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
                        hrs = (u - c).total_seconds() / 3600
                        if hrs >= 0:
                            durations.append(hrs)
                    except (ValueError, TypeError):
                        pass
            avg_ff = round(sum(durations) / len(durations), 1) if durations else None

            health = 10.0
            if comp_rate < 50: health -= 3
            elif comp_rate < 75: health -= 1
            if pending > 10: health -= 2
            elif pending > 5: health -= 1
            if avg_ff and avg_ff > 72: health -= 2
            elif avg_ff and avg_ff > 24: health -= 1
            health = max(1, min(10, round(health)))

            scorecards.append({
                "disaster_id": did, "title": d.get("title", "Unknown"), "type": d.get("type"),
                "severity": d.get("severity"), "total_requests": total_reqs, "completed": completed,
                "pending": pending, "in_progress": in_prog, "completion_rate": comp_rate,
                "avg_fulfillment_hours": avg_ff, "health_score": health,
                "affected_population": d.get("affected_population"), "casualties": d.get("casualties"),
            })

        scorecards.sort(key=lambda s: s["health_score"])
        return scorecards
    except Exception as e:
        logger.warning(f"Disaster scorecards failed: {e}")
        return []


async def _get_responder_performance() -> dict:
    """Track NGO and volunteer performance metrics."""
    try:
        assigned_resp = await db_admin.table("resource_requests").select(
            "assigned_to,status,created_at,updated_at"
        ).limit(500).async_execute()

        ngo_stats: dict[str, dict] = {}
        for r in (assigned_resp.data or []):
            ngo_id = r.get("assigned_to")
            if not ngo_id:
                continue
            if ngo_id not in ngo_stats:
                ngo_stats[ngo_id] = {"assigned": 0, "completed": 0, "in_progress": 0, "durations": []}
            ngo_stats[ngo_id]["assigned"] += 1
            status = r.get("status", "")
            if status in ("completed", "delivered"):
                ngo_stats[ngo_id]["completed"] += 1
                if r.get("created_at") and r.get("updated_at"):
                    try:
                        c = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                        u = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
                        hrs = (u - c).total_seconds() / 3600
                        if hrs >= 0:
                            ngo_stats[ngo_id]["durations"].append(hrs)
                    except (ValueError, TypeError):
                        pass
            elif status in ("assigned", "in_progress"):
                ngo_stats[ngo_id]["in_progress"] += 1

        ngo_ids = list(ngo_stats.keys())
        ngo_names: dict[str, str] = {}
        if ngo_ids:
            try:
                names_resp = await db_admin.table("users").select("id,full_name").in_("id", ngo_ids[:50]).async_execute()
                ngo_names = {str(u["id"]): u.get("full_name", "Unknown") for u in (names_resp.data or [])}
            except Exception:
                pass

        ngo_perf = []
        for ngo_id, stats in ngo_stats.items():
            avg_t = round(sum(stats["durations"]) / len(stats["durations"]), 1) if stats["durations"] else None
            ngo_perf.append({
                "id": ngo_id, "name": ngo_names.get(ngo_id, "Unknown"),
                "assigned": stats["assigned"], "completed": stats["completed"],
                "in_progress": stats["in_progress"],
                "completion_rate": round(stats["completed"] / max(stats["assigned"], 1) * 100, 1),
                "avg_fulfillment_hours": avg_t,
            })
        ngo_perf.sort(key=lambda x: x["completion_rate"], reverse=True)

        vol_count = 0
        try:
            vol_resp = await db_admin.table("volunteer_assignments").select(
                "volunteer_id", count="exact"
            ).limit(1).async_execute()
            vol_count = int(vol_resp.count or 0)
        except Exception:
            pass

        return {"ngo_performance": ngo_perf[:20], "total_ngos_active": len(ngo_perf), "total_volunteer_assignments": vol_count}
    except Exception as e:
        logger.warning(f"Responder performance failed: {e}")
        return {}


async def _get_user_account_snapshot(user_id: str) -> dict:
    """Get core user account data."""
    try:
        resp = (
            await db_admin.table("users")
            .select("id,full_name,email,role,metadata,created_at")
            .eq("id", user_id)
            .maybe_single()
            .async_execute()
        )
        return resp.data or {}
    except Exception as e:
        logger.warning(f"Failed to fetch current user account snapshot: {e}")
        return {}


async def _get_global_users_snapshot(include_pii: bool = False, limit: int = 200) -> dict:
    """Get live platform-wide users snapshot."""
    try:
        list_limit = min(max(limit, 1), 1000)
        list_fields = "id,full_name,email,role,created_at,is_profile_completed" if include_pii else "id,full_name,role,created_at"

        users_resp = (
            await db_admin.table("users")
            .select(list_fields, count="exact")
            .order("created_at", desc=True)
            .limit(list_limit)
            .async_execute()
        )
        users = users_resp.data or []
        total_users = int(users_resp.count or len(users))

        by_role: dict[str, int] = {}
        for u in users:
            role = u.get("role") or "unknown"
            by_role[role] = by_role.get(role, 0) + 1

        return {
            "total": total_users,
            "returned": len(users),
            "by_role": by_role,
            "users": users,
            "pii_included": include_pii,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch global users snapshot: {e}")
        return {"total": 0, "returned": 0, "by_role": {}, "users": [], "pii_included": include_pii}


async def _get_focused_disaster(disaster_id: str) -> dict:
    """Get detailed snapshot for a specific disaster."""
    try:
        resp = (
            await db.table("disasters")
            .select("id,title,type,severity,status,affected_population,casualties,location,description,created_at")
            .eq("id", disaster_id)
            .maybe_single()
            .async_execute()
        )
        return resp.data or {}
    except Exception as e:
        logger.warning(f"Failed to fetch focused disaster {disaster_id}: {e}")
        return {}


async def _get_full_context(user: dict, disaster_id: str | None = None, intent: str = "general") -> dict:
    """Pull relevant context from Supabase, pruned by intent."""
    context: dict = {}
    user_id = user.get("id")
    user_role = user.get("role", "")

    elevated_roles = {"admin", "coordinator", "super_admin"}
    user_role_normalized = str(user_role or "").lower()
    include_pii = user_role_normalized in elevated_roles

    # ── Parallel fetch: system-wide data ──────────────────────────────────────
    base_tasks = [
        _get_active_disasters(),
        _get_resource_requests_summary(),
        _get_inventory_summary(),
        _get_active_alerts(),
        _get_global_users_snapshot(include_pii=include_pii, limit=250),
    ]
    base_results = await asyncio.gather(*base_tasks, return_exceptions=True)

    context["active_disasters"] = base_results[0] if not isinstance(base_results[0], Exception) else []
    context["resource_requests_summary"] = base_results[1] if not isinstance(base_results[1], Exception) else {}
    context["inventory_summary"] = base_results[2] if not isinstance(base_results[2], Exception) else {}
    context["active_alerts"] = base_results[3] if not isinstance(base_results[3], Exception) else []
    context["platform_users"] = base_results[4] if not isinstance(base_results[4], Exception) else {}

    # ── Parallel fetch: admin-only insights ────────────────────────────────────
    if include_pii:
        admin_tasks = [
            _get_global_resource_requests(limit=300),
            _get_chatbot_intake_activity(),
            _get_request_lifecycle_metrics(),
            _get_activity_heatmap(),
            _get_supply_demand_gap(),
            _get_engagement_summary(),
            _get_user_registration_insights(),
            _get_request_pipeline_funnel(),
            _get_trend_analysis(),
            _get_geographic_insights(),
            _get_disaster_scorecards(),
            _get_responder_performance(),
        ]
        admin_results = await asyncio.gather(*admin_tasks, return_exceptions=True)

        context["global_resource_requests"] = admin_results[0] if not isinstance(admin_results[0], Exception) else []
        context["chatbot_intake_activity"] = admin_results[1] if not isinstance(admin_results[1], Exception) else {}
        context["request_lifecycle"] = admin_results[2] if not isinstance(admin_results[2], Exception) else {}
        context["activity_heatmap"] = admin_results[3] if not isinstance(admin_results[3], Exception) else {}
        context["supply_demand_gaps"] = admin_results[4] if not isinstance(admin_results[4], Exception) else {}
        context["engagement_summary"] = admin_results[5] if not isinstance(admin_results[5], Exception) else {}
        context["registration_insights"] = admin_results[6] if not isinstance(admin_results[6], Exception) else {}
        context["request_pipeline"] = admin_results[7] if not isinstance(admin_results[7], Exception) else {}
        context["trend_analysis"] = admin_results[8] if not isinstance(admin_results[8], Exception) else {}
        context["geographic_insights"] = admin_results[9] if not isinstance(admin_results[9], Exception) else {}
        context["disaster_scorecards"] = admin_results[10] if not isinstance(admin_results[10], Exception) else []
        context["responder_performance"] = admin_results[11] if not isinstance(admin_results[11], Exception) else {}

    if disaster_id:
        context["focused_disaster"] = await _get_focused_disaster(disaster_id)

    if not user_id:
        return context

    context["current_user"] = await _get_user_account_snapshot(user_id)

    # ── Role-specific personal data ───────────────────────────────────────────
    if user_role == "victim":
        try:
            rr = await db.table("resource_requests").select(
                "id,resource_type,status,priority,description,created_at,address_text,estimated_delivery"
            ).eq("victim_id", user_id).order("created_at", desc=True).limit(10).async_execute()
            context["user_requests"] = rr.data or []
        except Exception as e:
            logger.warning(f"victim resource_requests fetch failed: {e}")

    elif user_role == "ngo":
        try:
            ar = await db.table("resource_requests").select(
                "id,resource_type,status,priority,address_text,description"
            ).eq("assigned_to", user_id).in_("status", ["assigned", "in_progress"]).limit(20).async_execute()
            context["assigned_requests"] = ar.data or []
        except Exception as e:
            logger.warning(f"NGO assigned_requests fetch failed: {e}")

        try:
            inv = await db.table("resources").select(
                "type,quantity,status"
            ).eq("provider_id", user_id).eq("status", "available").async_execute()
            context["ngo_inventory"] = inv.data or []
        except Exception as e:
            logger.warning(f"NGO inventory fetch failed: {e}")

    elif user_role == "volunteer":
        try:
            va = await db.table("volunteer_assignments").select(
                "id,mobilization_id,status,assigned_at"
            ).eq("volunteer_id", user_id).in_("status", ["assigned", "active"]).limit(10).async_execute()
            context["volunteer_assignments"] = va.data or []
        except Exception as e:
            logger.warning(f"volunteer_assignments fetch failed: {e}")

    elif user_role == "donor":
        try:
            dp = await db.table("donor_pledges").select(
                "id,resource_type,quantity_pledged,status,created_at"
            ).eq("donor_id", user_id).order("created_at", desc=True).limit(10).async_execute()
            context["donor_pledges"] = dp.data or []
        except Exception as e:
            logger.warning(f"donor_pledges fetch failed: {e}")

    # ── Prune context by intent ───────────────────────────────────────────────
    context = _prune_context_by_intent(context, intent)

    return context


def _format_context_as_system_prompt(context: dict, user_info: dict | None = None) -> str:
    """Format live Supabase data as a system prompt for the LLM."""
    parts = [
        "You are DisasterGPT, an AI assistant embedded in a disaster management platform.",
        "Answer questions using ONLY the real-time data provided below.",
        "Be concise, data-driven, and action-oriented. Use markdown for formatting.",
    ]

    if user_info:
        role = user_info.get("role", "user")
        name = user_info.get("name") or "User"
        parts.append(f"\nThe person you are speaking with: {name} (role: {role})")

    current_user = context.get("current_user") or {}
    if current_user:
        meta = current_user.get("metadata") or {}
        parts.append(
            "\nCurrent user account (live Supabase): "
            f"id={current_user.get('id', '?')} | "
            f"name={current_user.get('full_name', user_info.get('name') if user_info else '?')} | "
            f"email={current_user.get('email', '?')} | "
            f"role={current_user.get('role', user_info.get('role') if user_info else '?')}"
        )
        if isinstance(meta, dict) and meta:
            points = meta.get("impact_points") or meta.get("total_impact_points")
            if points is not None:
                parts.append(f"Impact points: {points}")

    platform_users = context.get("platform_users") or {}
    if platform_users:
        total_users = int(platform_users.get("total") or 0)
        returned_users = int(platform_users.get("returned") or 0)
        pii_included = bool(platform_users.get("pii_included"))
        parts.append(
            "\nLive platform user accounts (Supabase users table): "
            f"total={total_users}, snapshot_rows={returned_users}, pii_included={pii_included}"
        )
        by_role = platform_users.get("by_role") or {}
        if by_role:
            parts.append("Users by role: " + ", ".join(f"{role}: {count}" for role, count in by_role.items()))
        users_list = platform_users.get("users") or []
        if users_list:
            parts.append("Recent user accounts snapshot:")
            for account in users_list[:20]:
                base = (
                    f"- {account.get('full_name') or 'Unknown'} "
                    f"(id={account.get('id', '?')}, role={account.get('role', 'unknown')})"
                )
                if pii_included and account.get("email"):
                    base += f" email={account.get('email')}"
                parts.append(base)

    parts.append("\n=== LIVE SYSTEM DATA ===")

    focused = context.get("focused_disaster") or {}
    if focused:
        parts.append("\n## Focused Disaster Context:")
        parts.append(
            f"- {focused.get('title', 'Unknown')} | ID: {focused.get('id', '?')} | "
            f"Type: {focused.get('type', '?')} | Severity: {focused.get('severity', '?')} | "
            f"Status: {focused.get('status', '?')} | Location: {focused.get('location', '?')}"
        )

    disasters = context.get("active_disasters", [])
    if disasters:
        parts.append(f"\n## Active Disasters ({len(disasters)}):")
        for d in disasters:
            parts.append(
                f"- {d.get('title','Unknown')} | Type: {d.get('type','?')} | "
                f"Severity: {d.get('severity','?')} | Casualties: {d.get('casualties','?')} | "
                f"Affected: {d.get('affected_population','?')}"
            )
    else:
        parts.append("\n## Active Disasters: None currently active")

    req = context.get("resource_requests_summary", {})
    parts.append(f"\n## Resource Requests (all-time): {req.get('total', 0)} total")
    parts.append(f"  Created in last 24h: {req.get('recent_24h_total', 0)}")
    if req.get("by_status"):
        parts.append("  By status: " + ", ".join(f"{k}: {v}" for k, v in req["by_status"].items()))
    if req.get("by_type"):
        parts.append("  By type (24h): " + ", ".join(f"{k}: {v}" for k, v in req["by_type"].items()))

    global_requests = context.get("global_resource_requests") or []
    if global_requests:
        parts.append(f"\n## Individual Resource Requests Snapshot ({len(global_requests)} rows):")
        for row in global_requests[:40]:
            parts.append(
                f"  - [{str(row.get('status', '?')).upper()}] {row.get('resource_type', '?')} "
                f"x{row.get('quantity', 1)} | priority={row.get('priority', '?')} | "
                f"victim={row.get('victim_name') or row.get('victim_id', '?')}"
                + (f" ({row.get('victim_email')})" if row.get('victim_email') else "")
            )

    inv = context.get("inventory_summary", {})
    parts.append(f"\n## Resource Inventory: {inv.get('total_resources', 0)} total entries")
    for rtype, data in (inv.get("by_type") or {}).items():
        qty = data.get("total_quantity", 0)
        flag = " ⚠️ LOW STOCK" if qty < 50 else ""
        parts.append(f"  - {rtype}: {qty} units{flag}")

    alerts = context.get("active_alerts", [])
    if alerts:
        parts.append(f"\n## Active Anomaly Alerts ({len(alerts)}):")
        for a in alerts:
            parts.append(f"  - [{a.get('severity','?').upper()}] {a.get('alert_type','?')}: {a.get('description','')}")
    else:
        parts.append("\n## Active Anomaly Alerts: None")

    # Admin-only sections (only included if pruned context still has them)
    for key, label in [
        ("chatbot_intake_activity", "Chatbot Intake Activity"),
        ("request_lifecycle", "Request Lifecycle Metrics"),
        ("activity_heatmap", "Request Activity Pattern"),
        ("supply_demand_gaps", "Supply vs Demand Gap Analysis"),
        ("engagement_summary", "User Engagement Summary"),
        ("registration_insights", "User Registration Trends"),
        ("request_pipeline", "Request Pipeline Funnel"),
        ("trend_analysis", "Week-over-Week Trends"),
        ("geographic_insights", "Geographic Insights"),
        ("disaster_scorecards", "Disaster Scorecards"),
        ("responder_performance", "Responder Performance"),
    ]:
        data = context.get(key)
        if data:
            parts.append(f"\n## {label}: {json.dumps(data, default=str)[:2000]}")

    if context.get("user_requests"):
        reqs = context["user_requests"]
        parts.append(f"\n## THIS USER'S Requests ({len(reqs)}):")
        for r in reqs[:5]:
            parts.append(
                f"  - [{r.get('status','?').upper()}] {r.get('resource_type','?')} "
                f"(priority: {r.get('priority','?')}) — {(r.get('description') or '')[:80]}"
            )

    if context.get("assigned_requests"):
        parts.append(f"\n## Requests Assigned to This NGO ({len(context['assigned_requests'])}):")
        for r in context["assigned_requests"][:5]:
            parts.append(f"  - [{r.get('status','?').upper()}] {r.get('resource_type','?')} at {r.get('address_text','?')}")

    parts.append("\n=== END OF LIVE DATA ===")
    parts.append("If data is missing or incomplete, say so clearly. Do not invent numbers.")

    return "\n".join(parts)


# ── Intent Handlers (same as original, with minor enhancements) ────────────────


async def _handle_resource_requests_intent(context: dict) -> tuple[str, dict]:
    summary = context.get("resource_requests_summary", {})
    total = summary.get("total", 0)
    recent_24h_total = summary.get("recent_24h_total", 0)
    by_status = summary.get("by_status", {})
    by_type = summary.get("by_type", {})
    global_requests = context.get("global_resource_requests", [])

    parts = ["## Resource Requests Summary\n"]
    parts.append(f"**Total Requests (All Time):** {total}\n")
    parts.append(f"**Created in Last 24h:** {recent_24h_total}\n\n")

    if by_status:
        parts.append("### By Status\n")
        for status, count in by_status.items():
            parts.append(f"- {status}: {count}\n")
        parts.append("\n")

    if by_type:
        parts.append("### By Type (Last 24h)\n")
        for req_type, count in by_type.items():
            parts.append(f"- {req_type}: {count}\n")

    if global_requests:
        parts.append("\n### Individual Requests (Latest)\n")
        for req in global_requests[:30]:
            parts.append(
                f"- [{str(req.get('status', '?')).upper()}] {req.get('resource_type', '?')} "
                f"x{req.get('quantity', 1)} | Priority: {req.get('priority', '?')} | "
                f"Victim: {req.get('victim_name') or req.get('victim_id', '?')}\n"
            )

    return "".join(parts), {"type": "resource_requests", "data": summary, "individual_count": len(global_requests)}


async def _handle_available_resources_intent(context: dict) -> tuple[str, dict]:
    summary = context.get("inventory_summary", {})
    total = summary.get("total_resources", 0)
    by_type = summary.get("by_type", {})

    parts = [f"## Available Resources Inventory\n"]
    parts.append(f"**Total Resource Entries:** {total}\n\n")

    if by_type:
        for res_type, data in by_type.items():
            parts.append(f"### {res_type}\n")
            parts.append(f"- Locations: {data['count']}\n")
            parts.append(f"- Total Units: {data['total_quantity']}\n\n")
    else:
        parts.append("No resources in inventory.\n")

    return "".join(parts), {"type": "available_resources", "data": summary}


async def _handle_disaster_status_intent(context: dict) -> tuple[str, dict]:
    disasters = context.get("active_disasters", [])

    parts = [f"## Active Disasters\n"]

    if disasters:
        parts.append(f"**Total Active:** {len(disasters)}\n\n")
        for d in disasters:
            parts.append(f"### {d.get('title', 'Unknown')}\n")
            parts.append(f"- **Type:** {d.get('type', 'N/A')}\n")
            parts.append(f"- **Severity:** {d.get('severity_score', 'N/A')}/10\n")
            parts.append(f"- **Status:** {d.get('status', 'N/A')}\n")
            parts.append(f"- **Location:** {d.get('location', 'N/A')}\n")
            parts.append(f"- **ID:** {d.get('id', 'N/A')}\n\n")
    else:
        parts.append("No active disasters.\n")

    return "".join(parts), {"type": "disaster_status", "data": {"disasters": disasters}}


async def _handle_allocate_resources_intent(message: str, context: dict) -> tuple[str, dict]:
    disasters = context.get("active_disasters", [])

    parts = ["## Resource Allocation\n"]
    parts.append("To allocate resources, you can use the `/api/resources/allocate` endpoint.\n\n")

    if disasters:
        parts.append("### Available Disasters for Allocation\n")
        for d in disasters[:5]:
            parts.append(f"- {d.get('title', 'Unknown')} (ID: {d.get('id', 'N/A')})\n")
        parts.append("\n")

    parts.append("### Example Request\n")
    parts.append("""```json
POST /api/resources/allocate
{
  "disaster_id": "<disaster-id>",
  "resource_requests": [
    {"resource_type": "Food", "quantity": 100},
    {"resource_type": "Water", "quantity": 200}
  ]
}
```""")

    return "".join(parts), {"type": "allocate_resources", "note": "User should use /api/resources/allocate endpoint"}


async def _handle_generate_report_intent(context: dict) -> tuple[str, dict]:
    disasters = context.get("active_disasters", [])

    parts = ["## Situation Report (SITREP)\n"]
    parts.append("To generate a full situation report, use the `/api/nlp/sitrep/generate` endpoint.\n\n")

    parts.append("### Current Summary\n")
    parts.append(f"- Active Disasters: {len(disasters)}\n")

    req_summary = context.get("resource_requests_summary", {})
    parts.append(f"- Resource Requests (24h): {req_summary.get('total', 0)}\n")

    inv_summary = context.get("inventory_summary", {})
    parts.append(f"- Available Resources: {inv_summary.get('total_resources', 0)}\n")

    alerts = context.get("active_alerts", [])
    parts.append(f"- Active Alerts: {len(alerts)}\n\n")

    parts.append("### Example Request\n")
    parts.append("""```json
POST /api/nlp/sitrep/generate
{
  "disaster_id": "<optional-disaster-id>"
}
```""")

    return "".join(parts), {"type": "generate_report", "note": "User should use /api/nlp/sitrep/generate"}


async def _handle_anomalies_intent(context: dict) -> tuple[str, dict]:
    alerts = context.get("active_alerts", [])

    parts = ["## Active Anomaly Alerts\n"]

    if alerts:
        parts.append(f"**Total Active Alerts:** {len(alerts)}\n\n")

        for severity in ["critical", "high", "medium", "low"]:
            sev_alerts = [a for a in alerts if a.get("severity") == severity]
            if sev_alerts:
                emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")
                parts.append(f"### {emoji} {severity.title()}\n")
                for a in sev_alerts:
                    parts.append(f"- **{a.get('alert_type', 'Unknown')}**: {a.get('description', 'No description')}\n")
                parts.append("\n")
    else:
        parts.append("No active anomaly alerts.\n")

    return "".join(parts), {"type": "anomalies", "data": {"alerts": alerts}}


async def _handle_users_overview_intent(context: dict, user: dict) -> tuple[str, dict]:
    users_ctx = context.get("platform_users") or {}
    total = int(users_ctx.get("total") or 0)
    by_role = users_ctx.get("by_role") or {}
    users = users_ctx.get("users") or []
    pii_included = bool(users_ctx.get("pii_included"))

    parts = ["## Platform User Accounts\n"]
    parts.append(f"**Total Users:** {total}\n\n")

    if by_role:
        parts.append("### By Role\n")
        for role, count in sorted(by_role.items(), key=lambda kv: kv[0]):
            parts.append(f"- {role}: {count}\n")
        parts.append("\n")

    if users:
        parts.append(f"### User Snapshot ({len(users)} records)\n")
        for account in users[:30]:
            line = f"- {account.get('full_name') or 'Unknown'} | role: {account.get('role', 'unknown')} | id: {account.get('id', '?')}"
            if pii_included and account.get("email"):
                line += f" | email: {account.get('email')}"
            parts.append(line + "\n")

    if not pii_included:
        parts.append("\n_PII is hidden for your role._\n")

    return "".join(parts), {"type": "users_overview", "data": {"total": total, "by_role": by_role}}


async def _handle_user_requests_intent(context: dict) -> tuple[str, dict]:
    requests = context.get("user_requests", [])
    if not requests:
        return (
            "You have no resource requests on file. You can submit a new request from the Requests section.",
            {"type": "user_requests", "count": 0},
        )
    STATUS_EMOJI = {"pending": "⏳", "approved": "✅", "assigned": "👷", "in_progress": "🔄", "delivered": "📦", "completed": "✅", "rejected": "❌"}
    parts = [f"## Your Requests ({len(requests)} found)\n"]
    for r in requests:
        emoji = STATUS_EMOJI.get(r.get("status", ""), "📋")
        status_label = (r.get("status") or "unknown").replace("_", " ").title()
        delivery = r.get("estimated_delivery")
        delivery_str = f" | ETA: {delivery[:10]}" if delivery else ""
        parts.append(
            f"{emoji} **{r.get('resource_type', '?')}** — {status_label}{delivery_str}\n"
            f"   Priority: {r.get('priority', '?')} | {(r.get('description') or '')[:100]}\n"
        )
    return "\n".join(parts), {"type": "user_requests", "count": len(requests)}


async def _handle_low_stock_intent(context: dict) -> tuple[str, dict]:
    inv = context.get("inventory_summary", {})
    low_types = inv.get("low_stock", [])
    by_type = inv.get("by_type", {})

    if not low_types:
        return ("✅ All tracked resource types currently have adequate stock levels (≥ 50 units each).", {"type": "low_stock", "count": 0})
    parts = [f"## ⚠️ Low Stock Alert — {len(low_types)} resource type(s) below threshold\n"]
    for rtype in sorted(low_types, key=lambda r: by_type.get(r, {}).get("total_quantity", 0)):
        qty = by_type.get(rtype, {}).get("total_quantity", 0)
        locs = by_type.get(rtype, {}).get("count", 0)
        parts.append(f"- **{rtype}**: {qty} units across {locs} location(s) — **restock needed**")
    parts.append("\nConsider issuing a procurement request or reallocating from lower-severity zones.")
    return "\n".join(parts), {"type": "low_stock", "items": low_types}


async def _handle_briefing_intent(context: dict) -> tuple[str, dict]:
    alerts_list: list[str] = []

    lifecycle = context.get("request_lifecycle") or {}
    stale_count = lifecycle.get("stale_count", 0)
    if stale_count > 0:
        alerts_list.append(f"🚨 **{stale_count} request(s)** pending for over 48 hours")

    gaps = context.get("supply_demand_gaps") or {}
    critical = gaps.get("critical_shortages", [])
    if critical:
        types = ", ".join(g["type"] for g in critical[:3])
        alerts_list.append(f"⚠️ **Critical shortages** in: {types}")

    chatbot = context.get("chatbot_intake_activity") or {}
    abandon_rate = chatbot.get("abandonment_rate", 0)
    if abandon_rate > 30:
        alerts_list.append(f"📉 **High chatbot abandonment** ({abandon_rate}%) — victims may be frustrated")

    anomalies = context.get("active_alerts") or []
    critical_anomalies = [a for a in anomalies if a.get("severity") == "critical"]
    if critical_anomalies:
        alerts_list.append(f"🔴 **{len(critical_anomalies)} critical anomaly alert(s)** active")

    disasters = context.get("active_disasters") or []
    if disasters:
        alerts_list.append(f"🌍 **{len(disasters)} active disaster(s)** being tracked")

    req = context.get("resource_requests_summary") or {}
    pending = req.get("by_status", {}).get("pending", 0)
    if pending > 10:
        alerts_list.append(f"📋 **{pending} pending requests** awaiting action")

    if alerts_list:
        parts = ["## ⚡ Admin Briefing — Items Requiring Attention\n"]
        for alert in alerts_list:
            parts.append(f"- {alert}\n")
        parts.append("\n*Ask me about any of these for more details.*")
        return "\n".join(parts), {"type": "briefing", "alert_count": len(alerts_list)}

    return ("✅ **All clear.** No critical issues detected. System is operating within normal parameters.", {"type": "briefing", "alert_count": 0})


async def _handle_supply_demand_gap_intent(context: dict) -> tuple[str, dict]:
    gaps_data = context.get("supply_demand_gaps") or {}
    gap_list = gaps_data.get("gaps", [])

    parts = ["## Supply vs Demand Gap Analysis\n"]
    parts.append(
        f"**Total Active Demand:** {gaps_data.get('total_demand', 0)} units | "
        f"**Total Available Supply:** {gaps_data.get('total_supply', 0)} units\n"
    )

    if gap_list:
        parts.append("\n| Resource Type | Demand | Supply | Gap | Coverage | Status |")
        parts.append("|---|---|---|---|---|---|")
        for g in gap_list:
            flag = " ⚠️" if g["coverage_pct"] < 50 else ""
            parts.append(
                f"| {g['type']} | {g['demand']} | {g['supply']} | "
                f"{g['gap']} | {g['coverage_pct']}% | {g['status'].upper()}{flag} |"
            )
        parts.append("")

        critical = gaps_data.get("critical_shortages", [])
        if critical:
            parts.append(f"\n### 🚨 Critical Shortages ({len(critical)} types below 50% coverage)\n")
            for c in critical:
                parts.append(
                    f"- **{c['type']}**: only {c['supply']} available "
                    f"against {c['demand']} demanded ({c['coverage_pct']}% coverage)"
                )
    else:
        parts.append("\n*No active demand or supply data available.*")

    return "\n".join(parts), {"type": "supply_demand_gap", "data": gaps_data}


async def _handle_request_lifecycle_intent(context: dict) -> tuple[str, dict]:
    lifecycle = context.get("request_lifecycle") or {}

    parts = ["## Request Lifecycle & Fulfillment Metrics\n"]

    if lifecycle.get("sample_size", 0) > 0:
        parts.append(f"**Median Fulfillment Time:** {lifecycle.get('median_fulfillment_hours', '?')} hours\n")
        parts.append(f"**Average Fulfillment Time:** {lifecycle.get('avg_fulfillment_hours', '?')} hours\n")
        parts.append(f"**Sample Size:** {lifecycle.get('sample_size', 0)} completed requests\n")

        by_priority = lifecycle.get("by_priority", {})
        if by_priority:
            parts.append("\n### Average Fulfillment by Priority\n")
            for pri, hrs in sorted(by_priority.items()):
                parts.append(f"- **{pri}**: {hrs} hours\n")
    else:
        parts.append("*No completed request data available for lifecycle analysis.*\n")

    stale_count = lifecycle.get("stale_count", 0)
    if stale_count > 0:
        parts.append(f"\n### ⚠️ Stale Requests ({stale_count} pending > 48 hours)\n")
        for sr in lifecycle.get("stale_pending_requests", []):
            parts.append(f"- **ID:** {sr['id']} | **Age:** {sr['age_hours']}h | **Priority:** {sr.get('priority', '?')}\n")
    else:
        parts.append("\n### ✅ No stale requests — all pending requests are less than 48 hours old.\n")

    return "\n".join(parts), {"type": "request_lifecycle", "data": lifecycle}


async def _handle_chatbot_activity_intent(context: dict) -> tuple[str, dict]:
    chatbot = context.get("chatbot_intake_activity") or {}

    parts = [f"## Victim Chatbot Intake Activity (Last {chatbot.get('time_range_hours', 24)}h)\n"]

    total = chatbot.get("total_sessions", 0)
    completed = chatbot.get("completed", 0)
    abandoned = chatbot.get("abandoned", 0)
    abandon_rate = chatbot.get("abandonment_rate", 0)

    parts.append(f"**Total Sessions:** {total}\n")
    parts.append(f"**Completed:** {completed} | **Abandoned:** {abandoned}\n")
    parts.append(f"**Abandonment Rate:** {abandon_rate}%\n")

    demand = chatbot.get("resource_demand", {})
    if demand:
        parts.append("\n### Resource Demand from Chatbot\n")
        for rt, count in sorted(demand.items(), key=lambda x: x[1], reverse=True):
            parts.append(f"- **{rt}**: {count} requests\n")

    if total == 0:
        parts.append("\n*No chatbot sessions recorded in this time period.*\n")

    return "\n".join(parts), {"type": "chatbot_activity", "data": chatbot}


async def _handle_activity_heatmap_intent(context: dict) -> tuple[str, dict]:
    heatmap = context.get("activity_heatmap") or {}

    parts = [f"## Request Activity Patterns (Last {heatmap.get('days_analyzed', 7)} days)\n"]

    total = heatmap.get("total_requests", 0)
    parts.append(f"**Total Requests Analyzed:** {total}\n")

    if total > 0:
        if heatmap.get("peak_hour") is not None:
            parts.append(f"**Peak Hour:** {heatmap['peak_hour']}:00 UTC\n")
        if heatmap.get("peak_day"):
            parts.append(f"**Peak Day:** {heatmap['peak_day']}\n")

        daily = heatmap.get("daily_distribution", {})
        if daily:
            parts.append("\n### Daily Distribution\n")
            for day, count in sorted(daily.items(), key=lambda x: x[1], reverse=True):
                bar = "█" * min(count, 30)
                parts.append(f"- **{day}**: {count} requests {bar}\n")
    else:
        parts.append("\n*No request data available for the selected period.*\n")

    return "\n".join(parts), {"type": "activity_heatmap", "data": heatmap}


async def _handle_engagement_intent(context: dict) -> tuple[str, dict]:
    engagement = context.get("engagement_summary") or {}
    users_ctx = context.get("platform_users") or {}
    by_role = users_ctx.get("by_role", {})

    parts = ["## User Engagement Summary\n"]

    active_victims = engagement.get("active_victims_7d", 0)
    active_volunteers = engagement.get("active_volunteers_30d", 0)
    active_donors = engagement.get("active_donors_30d", 0)
    total_victims = by_role.get("victim", 0)
    total_volunteers = by_role.get("volunteer", 0)
    total_donors = by_role.get("donor", 0)

    parts.append("### Victims (7-day window)\n")
    pct_v = round(active_victims / max(total_victims, 1) * 100, 1)
    parts.append(f"- **Active:** {active_victims} / {total_victims} ({pct_v}%)\n")

    parts.append("\n### Volunteers (30-day window)\n")
    pct_vol = round(active_volunteers / max(total_volunteers, 1) * 100, 1)
    parts.append(f"- **Active:** {active_volunteers} / {total_volunteers} ({pct_vol}%)\n")

    parts.append("\n### Donors (30-day window)\n")
    pct_d = round(active_donors / max(total_donors, 1) * 100, 1)
    parts.append(f"- **Active:** {active_donors} / {total_donors} ({pct_d}%)\n")

    return "\n".join(parts), {"type": "engagement", "data": engagement}


async def _handle_registration_trends_intent(context: dict) -> tuple[str, dict]:
    reg = context.get("registration_insights") or {}
    users_ctx = context.get("platform_users") or {}

    parts = ["## 📊 User Registration & Growth\n"]
    parts.append(f"**Total Platform Users:** {users_ctx.get('total', 0)}\n")

    by_role = users_ctx.get("by_role", {})
    if by_role:
        parts.append("### Role Distribution\n")
        for role, count in sorted(by_role.items(), key=lambda x: x[1], reverse=True):
            parts.append(f"- **{role.title()}**: {count}\n")

    new_7d = reg.get("new_users_7d", 0)
    new_30d = reg.get("new_users_30d", 0)
    parts.append(f"\n### Recent Signups\n")
    parts.append(f"- **This week:** {new_7d} new users\n")
    parts.append(f"- **This month:** {new_30d} new users\n")

    incomplete = reg.get("incomplete_profiles", 0)
    if incomplete > 0:
        parts.append(f"\n### ⚠️ Incomplete Profiles\n")
        parts.append(f"**{incomplete} users** have not completed their profile setup.\n")

    return "\n".join(parts), {"type": "registration_trends", "data": reg}


async def _handle_request_pipeline_intent(context: dict) -> tuple[str, dict]:
    pipeline = context.get("request_pipeline") or {}

    parts = ["## 🔄 Request Pipeline Funnel\n"]

    total = pipeline.get("total", 0)
    if total == 0:
        parts.append("*No resource requests in the system yet.*\n")
        return "\n".join(parts), {"type": "request_pipeline", "data": pipeline}

    parts.append(f"**Total Requests:** {total}\n")
    parts.append(
        f"**Completion Rate:** {pipeline.get('completion_rate', 0)}% | "
        f"**Rejection Rate:** {pipeline.get('rejection_rate', 0)}% | "
        f"**Actively Processing:** {pipeline.get('active_processing_pct', 0)}%\n"
    )

    funnel = pipeline.get("funnel", {})
    if funnel:
        stages = ["pending", "approved", "assigned", "in_progress", "delivered", "completed", "rejected"]
        parts.append("\n### Status Breakdown\n")
        parts.append("| Stage | Count | % of Total |")
        parts.append("|---|---|---|")
        for s in stages:
            count = funnel.get(s, 0)
            if count > 0:
                pct = round(count / max(total, 1) * 100, 1)
                parts.append(f"| {s.replace('_', ' ').title()} | {count} | {pct}% |")
        parts.append("")

    pending = pipeline.get("pending_count", 0)
    if pending > 0:
        parts.append(f"\n### ⏳ Action Needed\n")
        parts.append(f"**{pending} requests** are still pending and awaiting processing.\n")

    return "\n".join(parts), {"type": "request_pipeline", "data": pipeline}


async def _handle_trends_intent(context: dict) -> tuple[str, dict]:
    trends = context.get("trend_analysis") or {}

    parts = ["## 📈 Week-over-Week Trend Analysis\n"]

    if not trends:
        parts.append("*No trend data available.*\n")
        return "\n".join(parts), {"type": "trends", "data": {}}

    for metric_key, data in trends.items():
        if not isinstance(data, dict):
            continue
        label = metric_key.replace("_", " ").title()
        trend = data.get("trend", "→")
        tw = data.get("this_week", 0)
        lw = data.get("last_week", 0)
        pct = data.get("change_pct", 0)
        emoji = "🟢" if trend == "↑" else ("🔴" if trend == "↓" else "⚪")
        parts.append(f"### {emoji} {label}\n")
        parts.append(f"- **This week:** {tw} | **Last week:** {lw}\n")
        parts.append(f"- **Change:** {data.get('change', 0):+} ({pct:+}%) {trend}\n")

    return "\n".join(parts), {"type": "trends", "data": trends}


async def _handle_geographic_intent(context: dict) -> tuple[str, dict]:
    geo = context.get("geographic_insights") or {}

    parts = [f"## 🌍 Geographic Insights ({geo.get('total_locations', 0)} locations)\n"]

    top_locs = geo.get("top_locations", [])
    if top_locs:
        parts.append("### Top Locations by Request Volume\n")
        parts.append("| Location | Total | Pending | Completed | High Priority |")
        parts.append("|---|---|---|---|---|")
        for loc in top_locs[:12]:
            parts.append(
                f"| {loc['location']} | {loc['total']} | {loc['pending']} | "
                f"{loc['completed']} | {loc['high_priority']} |"
            )
        parts.append("")

    underserved = geo.get("underserved_areas", [])
    if underserved:
        parts.append(f"\n### ⚠️ Underserved Areas ({len(underserved)} detected)\n")
        for u in underserved:
            parts.append(f"- **{u['location']}**: {u['pending_requests']} pending requests, only {u['available_resources']} resources available\n")

    return "\n".join(parts), {"type": "geographic", "data": geo}


async def _handle_disaster_comparison_intent(context: dict) -> tuple[str, dict]:
    scorecards = context.get("disaster_scorecards") or []

    parts = ["## 🏆 Disaster Performance Scorecards\n"]

    if not scorecards:
        parts.append("*No active disasters to compare.*\n")
        return "\n".join(parts), {"type": "disaster_comparison", "data": []}

    parts.append("| Disaster | Health | Completion | Pending | In Progress | Avg Fulfillment |")
    parts.append("|---|---|---|---|---|---|")
    for sc in scorecards:
        health_emoji = "🟢" if sc["health_score"] >= 8 else ("🟡" if sc["health_score"] >= 5 else "🔴")
        parts.append(
            f"| {sc['title']} | {health_emoji} {sc['health_score']}/10 | "
            f"{sc['completion_rate']}% | {sc['pending']} | {sc['in_progress']} | "
            f"{sc.get('avg_fulfillment_hours', 'N/A')}h |"
        )
    parts.append("")

    return "\n".join(parts), {"type": "disaster_comparison", "data": scorecards}


async def _handle_responder_performance_intent(context: dict) -> tuple[str, dict]:
    resp_data = context.get("responder_performance") or {}

    parts = ["## 👥 Responder Performance\n"]

    ngo_perf = resp_data.get("ngo_performance", [])
    if ngo_perf:
        parts.append(f"### NGO Performance ({resp_data.get('total_ngos_active', 0)} active)\n")
        parts.append("| NGO | Assigned | Completed | Rate | Avg Time | In Progress |")
        parts.append("|---|---|---|---|---|---|")
        for ngo in ngo_perf[:15]:
            parts.append(
                f"| {ngo['name']} | {ngo['assigned']} | {ngo['completed']} | "
                f"{ngo['completion_rate']}% | {ngo.get('avg_fulfillment_hours', 'N/A')}h | "
                f"{ngo['in_progress']} |"
            )
        parts.append("")
    else:
        parts.append("*No NGO assignment data available.*\n")

    return "\n".join(parts), {"type": "responder_performance", "data": resp_data}


async def _handle_causal_intent(message: str, context: dict) -> tuple[str, dict]:
    """Handle causal reasoning and explainability questions."""
    from ml.causal_model import DisasterCausalModel
    from app.services.explainability_service import ExplainabilityService

    explainability = ExplainabilityService()
    parts = ["## 🔬 Causal Analysis\n"]

    try:
        causal_model = await DisasterCausalModel.from_database()

        # Check if asking about root causes
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in ["root cause", "why did", "cause of", "what caused"]):
            outcome_var = "casualties"
            if "damage" in msg_lower or "economic" in msg_lower:
                outcome_var = "economic_damage_usd"

            root_causes = causal_model.rank_root_causes(outcome_var)
            if root_causes:
                parts.append(f"### Top Root Causes of {outcome_var.replace('_', ' ').title()}\n")
                for i, cause in enumerate(root_causes[:5], 1):
                    explanation = await explainability.explain_causal_insight(
                        treatment=cause.treatment,
                        outcome=outcome_var,
                        ate=cause.ate,
                        confidence_interval=cause.confidence_interval,
                        refutation_passed=cause.refutation_passed,
                    )
                    parts.append(f"**{i}. {cause.treatment.replace('_', ' ').title()}**\n")
                    parts.append(f"- ATE: {cause.ate:.4f}")
                    if cause.refutation_passed:
                        parts.append(f"- ✅ Causal (refutation passed)")
                    elif cause.refutation_passed is False:
                        parts.append(f"- ⚠️ May be confounded")
                    parts.append("")

        # Check if asking about counterfactuals
        elif any(kw in msg_lower for kw in ["what if", "counterfactual", "would have", "if we had"]):
            observation = {
                "weather_severity": 7.0,
                "disaster_type": 6.0,
                "response_time_hours": 12.0,
                "resource_availability": 5.0,
                "ngo_proximity_km": 50.0,
                "resource_quality_score": 5.0,
                "casualties": 20.0,
                "economic_damage_usd": 500000.0,
            }

            interventions = causal_model.top_counterfactual_interventions(observation, outcome_var="casualties", k=3)
            if interventions:
                parts.append("### Top Interventions to Reduce Casualties\n")
                for i, intervention in enumerate(interventions, 1):
                    parts.append(f"**{i}. Change {intervention['variable'].replace('_', ' ').title()}**\n")
                    parts.append(f"- Current: {intervention['current_value']}")
                    parts.append(f"- Proposed: {intervention['proposed_value']}")
                    parts.append(f"- Estimated reduction: {intervention['estimated_reduction']:.1f} casualties")
                    parts.append(f"- {intervention['explanation']}")
                    parts.append("")

        # Check if asking to explain priority/decision
        elif any(kw in msg_lower for kw in ["explain why", "explain priority", "reasoning behind", "justify"]):
            parts.append("### Priority Explanation Framework\n")
            parts.append("Our AI explains priority assignments using these factors:\n")
            for factor_key, factor_info in explainability.PRIORITY_FACTORS.items():
                parts.append(f"- **{factor_info['label']}**: {factor_info['impact']}")
                parts.append(f"  _{factor_info['description']}_")
            parts.append("")
            parts.append("*Ask me to explain a specific request's priority for detailed reasoning.*")

        # Default: show ATE estimates
        else:
            parts.append("### Causal Effect Estimates\n")
            parts.append("Key causal relationships in disaster outcomes:\n")

            estimates = [
                ("response_time_hours", "casualties"),
                ("resource_availability", "casualties"),
                ("resource_availability", "economic_damage_usd"),
                ("ngo_proximity_km", "response_time_hours"),
            ]

            for treatment, outcome in estimates:
                try:
                    est = causal_model.estimate_ate(treatment, outcome, compute_ci=False)
                    explanation = await explainability.explain_causal_insight(
                        treatment=treatment,
                        outcome=outcome,
                        ate=est.ate,
                        confidence_interval=est.confidence_interval,
                        refutation_passed=est.refutation_passed,
                    )
                    parts.append(f"#### {treatment.replace('_', ' ').title()} → {outcome.replace('_', ' ').title()}")
                    parts.append(f"- Effect: {est.ate:+.4f} per unit change")
                    if est.refutation_passed:
                        parts.append(f"- ✅ Causal relationship validated")
                    elif est.refutation_passed is False:
                        parts.append(f"- ⚠️ May involve confounding")
                    parts.append("")
                except Exception:
                    continue

            parts.append("*Ask 'what if we reduced response time?' for counterfactual analysis.*")

        return "\n".join(parts), {"type": "causal", "data": {"analysis_complete": True}}

    except Exception as e:
        logger.error(f"Causal analysis failed: {e}")
        return (
            f"## Causal Analysis Unavailable\n\n"
            f"The causal model requires more disaster data to produce reliable estimates. "
            f"Currently using synthetic data for demonstration.\n\n"
            f"*Error: {str(e)[:200]}*"
        ), {"type": "causal", "error": str(e)}


async def _handle_digest_intent(context: dict) -> tuple[str, dict]:
    parts = ["## 📋 Comprehensive Operations Digest\n"]
    parts.append(f"*Generated at {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}*\n")

    trends = context.get("trend_analysis") or {}
    if trends:
        parts.append("### 📈 Trends (Week-over-Week)\n")
        for key, data in trends.items():
            if isinstance(data, dict):
                parts.append(f"- {key.replace('_', ' ').title()}: {data.get('this_week', 0)} {data.get('trend', '→')} ({data.get('change_pct', 0):+}%)\n")

    disasters = context.get("active_disasters") or []
    parts.append(f"\n### 🌍 Active Disasters: {len(disasters)}\n")
    for d in disasters[:5]:
        parts.append(f"- {d.get('title', '?')} (severity: {d.get('severity', '?')})\n")

    req = context.get("resource_requests_summary") or {}
    parts.append(f"\n### 📦 Requests\n")
    parts.append(f"- Total: {req.get('total', 0)} | Last 24h: {req.get('recent_24h_total', 0)}\n")

    gaps = context.get("supply_demand_gaps") or {}
    critical = gaps.get("critical_shortages", [])
    if critical:
        parts.append(f"\n### ⚠️ Critical Shortages ({len(critical)})\n")
        for c in critical[:5]:
            parts.append(f"- **{c['type']}**: {c['coverage_pct']}% coverage\n")

    scorecards = context.get("disaster_scorecards") or []
    if scorecards:
        parts.append("\n### 🏆 Disaster Scorecards\n")
        for sc in scorecards[:5]:
            emoji = "🟢" if sc["health_score"] >= 8 else ("🟡" if sc["health_score"] >= 5 else "🔴")
            parts.append(f"- {emoji} {sc['title']}: health {sc['health_score']}/10, {sc['completion_rate']}% complete\n")

    alerts = context.get("active_alerts") or []
    if alerts:
        critical_alerts = [a for a in alerts if a.get("severity") == "critical"]
        parts.append(f"\n### 🚨 Alerts: {len(alerts)} active ({len(critical_alerts)} critical)\n")

    parts.append("\n---\n*Ask about any section for more details.*")
    return "\n".join(parts), {"type": "digest", "sections": 9}


async def _handle_general_intent(
    message: str,
    context: dict,
    history: list[dict],
    user_info: dict | None = None,
    conversation_summary: str | None = None,
) -> tuple[str, dict]:
    """Handle general questions using Groq with injected live Supabase context."""
    try:
        from groq import Groq
    except ImportError:
        logger.error("groq package not installed. Run: pip install groq")
        return _format_context_as_system_prompt(context, user_info), {"fallback": "no_groq_package"}

    system_prompt = _format_context_as_system_prompt(context, user_info)

    messages = []

    # Add conversation summary if available
    if conversation_summary:
        messages.append({
            "role": "system",
            "content": f"[Previous conversation summary]: {conversation_summary}",
        })

    for msg in history[-6:]:
        role = msg.get("role")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    api_key = os.environ.get("GROQ_API_KEY")
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    if not api_key:
        logger.error("GROQ_API_KEY env var not set")
        return (
            "I can see the live disaster data but my AI response engine is not configured (GROQ_API_KEY missing).",
            {"fallback": "no_api_key"},
        )

    try:
        client = Groq(api_key=api_key)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
                max_tokens=1024,
                temperature=0.35,
            ),
        )
        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            raise RuntimeError("Groq returned an empty response")
        return answer, {"type": "general", "llm": "groq", "model": model}
    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        disasters = context.get("active_disasters", [])
        req = context.get("resource_requests_summary", {})
        inv = context.get("inventory_summary", {})
        alerts = context.get("active_alerts", [])
        low = inv.get("low_stock", [])
        fallback_msg = (
            f"## Live System Summary\n\n"
            f"**Active disasters:** {len(disasters)}\n"
            f"**Resource requests (24h):** {req.get('total', 0)}\n"
            f"**Pending requests:** {req.get('by_status', {}).get('pending', 0)}\n"
            f"**Total inventory entries:** {inv.get('total_resources', 0)}\n"
            f"**Active alerts:** {len(alerts)}\n"
        )
        if low:
            fallback_msg += f"**⚠️ Low stock items:** {', '.join(low)}\n"
        fallback_msg += "\n*AI response engine temporarily unavailable. Showing raw data summary.*"
        return fallback_msg, {"type": "general", "fallback": "api_error", "error": str(e)}


# ── Chat Endpoints ──────────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """
    Chat with DisasterGPT (Enhanced V2).
    - Persists sessions and messages to DB
    - Uses semantic intent classification
    - Prunes context by intent for faster responses
    - Includes conversation memory with summarization
    - Returns follow-up suggestion chips and action cards
    """
    logger.info(
        "Chat request user=%s role=%s session=%s: %.80s...",
        user.get("id", "?"),
        user.get("role", "?"),
        body.session_id or "new",
        body.message,
    )

    # Merge JWT user with frontend hints
    if body.user_context:
        if body.user_context.role and not user.get("role"):
            user["role"] = body.user_context.role
        if body.user_context.name:
            user["name"] = body.user_context.name
        if body.user_context.user_id and not user.get("id"):
            user["id"] = body.user_context.user_id

    # Session management — prefer DB, fall back to in-memory
    session_id = body.session_id or str(uuid.uuid4())

    # Persist session to DB (background)
    background_tasks.add_task(_persist_session, session_id, user)

    # Load history from DB first, fall back to in-memory
    history = await _get_session_history_from_db(session_id)
    if not history:
        _, session_data = _get_or_create_session(session_id)
        history = session_data.get("messages", [])

    # Get conversation summary from DB
    conversation_summary = await _get_conversation_summary_from_db(session_id)

    # Add user message to in-memory session
    _add_message_to_session(session_id, "user", body.message)

    # Classify intent FIRST (before pulling context, so we can prune)
    intent = _classify_intent(body.message)
    logger.info("Detected intent=%s for user=%s role=%s", intent, user.get("id", "?"), user.get("role", "?"))

    # Pull live context (pruned by intent)
    disaster_id = body.context.disaster_id if body.context else None
    context = await _get_full_context(user, disaster_id, intent=intent)

    # Detect intent and route
    response_text = ""
    context_data: dict | None = None

    try:
        elevated_roles = {"admin", "coordinator", "super_admin"}
        user_role_normalized = str(user.get("role") or "").lower()
        force_live_llm = user_role_normalized in elevated_roles

        if intent == "user_requests":
            response_text, context_data = await _handle_user_requests_intent(context)
        elif intent == "low_stock":
            response_text, context_data = await _handle_low_stock_intent(context)
        elif intent == "resource_requests":
            response_text, context_data = await _handle_resource_requests_intent(context)
        elif intent == "users_overview":
            response_text, context_data = await _handle_users_overview_intent(context, user)
        elif intent == "available_resources":
            response_text, context_data = await _handle_available_resources_intent(context)
        elif intent == "disaster_status":
            response_text, context_data = await _handle_disaster_status_intent(context)
        elif intent == "allocate_resources":
            response_text, context_data = await _handle_allocate_resources_intent(body.message, context)
        elif intent == "generate_report":
            response_text, context_data = await _handle_generate_report_intent(context)
        elif intent == "anomalies":
            response_text, context_data = await _handle_anomalies_intent(context)
        elif intent == "briefing":
            response_text, context_data = await _handle_briefing_intent(context)
        elif intent == "supply_demand_gap":
            response_text, context_data = await _handle_supply_demand_gap_intent(context)
        elif intent == "request_lifecycle":
            response_text, context_data = await _handle_request_lifecycle_intent(context)
        elif intent == "chatbot_activity":
            response_text, context_data = await _handle_chatbot_activity_intent(context)
        elif intent == "activity_heatmap":
            response_text, context_data = await _handle_activity_heatmap_intent(context)
        elif intent == "engagement":
            response_text, context_data = await _handle_engagement_intent(context)
        elif intent == "registration_trends":
            response_text, context_data = await _handle_registration_trends_intent(context)
        elif intent == "request_pipeline":
            response_text, context_data = await _handle_request_pipeline_intent(context)
        elif intent == "trends":
            response_text, context_data = await _handle_trends_intent(context)
        elif intent == "geographic":
            response_text, context_data = await _handle_geographic_intent(context)
        elif intent == "disaster_comparison":
            response_text, context_data = await _handle_disaster_comparison_intent(context)
        elif intent == "responder_performance":
            response_text, context_data = await _handle_responder_performance_intent(context)
        elif intent == "causal":
            response_text, context_data = await _handle_causal_intent(body.message, context)
        elif intent == "digest":
            response_text, context_data = await _handle_digest_intent(context)
        else:
            user_info = {
                "role": user.get("role"),
                "name": user.get("name"),
                "user_requests": context.get("user_requests", []),
            }
            response_text, context_data = await _handle_general_intent(
                body.message, context, history, user_info, conversation_summary
            )

        # Force live LLM for admin/coordinator on non-structured intents
        structured_insight_intents = {
            "briefing", "supply_demand_gap", "request_lifecycle",
            "chatbot_activity", "activity_heatmap", "engagement",
            "registration_trends", "request_pipeline",
            "trends", "geographic", "disaster_comparison",
            "responder_performance", "digest",
        }
        if force_live_llm and intent != "general" and intent not in structured_insight_intents:
            user_info = {
                "role": user.get("role"),
                "name": user.get("name"),
                "user_requests": context.get("user_requests", []),
            }
            response_text, context_data = await _handle_general_intent(
                body.message, context, history, user_info, conversation_summary
            )
            if isinstance(context_data, dict):
                context_data["intent_routed"] = intent
                context_data["mode"] = "forced_live_llm"
    except Exception as e:
        logger.error(f"Error handling intent {intent}: {e}", exc_info=True)
        response_text = f"I encountered an error while processing your request. Error: {str(e)[:200]}"
        context_data = {"error": str(e), "intent": intent}

    # Add assistant message to in-memory session
    _add_message_to_session(session_id, "assistant", response_text)

    # Generate follow-up suggestions and action cards
    user_role = user.get("role", "user")
    follow_up_suggestions = _generate_follow_up_suggestions(intent, context_data, user_role)
    action_cards = _generate_action_cards(intent, context_data, user_role)

    # Persist messages and update summary in background
    background_tasks.add_task(
        _persist_message,
        session_id,
        "user",
        body.message,
        intent=intent,
    )
    background_tasks.add_task(
        _persist_message,
        session_id,
        "assistant",
        response_text,
        intent=intent,
        context_data=context_data,
        follow_up_suggestions=follow_up_suggestions,
        action_cards=action_cards,
    )

    # Update conversation summary in background if enough messages
    if len(history) >= 6:
        background_tasks.add_task(_update_conversation_summary, session_id, history)

    return ChatResponse(
        message=response_text,
        session_id=session_id,
        intent=intent,
        context_data=context_data,
        follow_up_suggestions=follow_up_suggestions,
        action_cards=action_cards,
    )


# ── Streaming Chat Endpoint ────────────────────────────────────────────────────


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """
    Streaming chat endpoint — returns SSE events for real-time responses.

    Event types:
      - meta: Intent classification and session info
      - token: Individual response tokens (for LLM-generated responses)
      - context_data: Structured data used for the response
      - follow_up: Follow-up suggestion chips
      - action_cards: Actionable cards with confirm buttons
      - done: Stream complete with final metadata
    """
    logger.info(
        "Chat stream request user=%s session=%s: %.80s...",
        user.get("id", "?"),
        body.session_id or "new",
        body.message,
    )

    # Merge frontend hints
    if body.user_context:
        if body.user_context.role and not user.get("role"):
            user["role"] = body.user_context.role
        if body.user_context.name:
            user["name"] = body.user_context.name

    session_id = body.session_id or str(uuid.uuid4())

    async def event_generator():
        try:
            # Persist session
            await _persist_session(session_id, user)

            # Load history
            history = await _get_session_history_from_db(session_id)
            if not history:
                _, session_data = _get_or_create_session(session_id)
                history = session_data.get("messages", [])

            conversation_summary = await _get_conversation_summary_from_db(session_id)

            _add_message_to_session(session_id, "user", body.message)

            # Classify intent
            intent = _classify_intent(body.message)

            # Emit metadata
            yield f"data: {json.dumps({'type': 'meta', 'intent': intent, 'session_id': session_id})}\n\n"

            # Pull context
            disaster_id = body.context.disaster_id if body.context else None
            context = await _get_full_context(user, disaster_id, intent=intent)

            # Route to handler
            response_text = ""
            context_data: dict | None = None

            # Check if this intent should use streaming LLM
            general_intents = {"general", "causal", "multi_agent"}
            if intent in general_intents:
                # Stream the LLM response
                user_info = {
                    "role": user.get("role"),
                    "name": user.get("name"),
                    "user_requests": context.get("user_requests", []),
                }
                system_prompt = _format_context_as_system_prompt(context, user_info)

                try:
                    from groq import Groq

                    api_key = os.environ.get("GROQ_API_KEY")
                    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

                    if api_key:
                        client = Groq(api_key=api_key)

                        messages = []
                        if conversation_summary:
                            messages.append({"role": "system", "content": f"[Previous conversation summary]: {conversation_summary}"})
                        for msg in history[-6:]:
                            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                                messages.append({"role": msg["role"], "content": msg["content"]})
                        messages.append({"role": "user", "content": body.message})

                        def _stream():
                            return client.chat.completions.create(
                                model=model,
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    *messages,
                                ],
                                max_tokens=1024,
                                temperature=0.35,
                                stream=True,
                            )

                        loop = asyncio.get_event_loop()
                        stream = await loop.run_in_executor(None, _stream)

                        import queue
                        import threading

                        q: queue.Queue = queue.Queue()
                        sentinel = object()

                        def _run():
                            try:
                                for chunk in stream:
                                    if chunk.choices and chunk.choices[0].delta.content:
                                        q.put(chunk.choices[0].delta.content)
                            except Exception as exc:
                                q.put(exc)
                            finally:
                                q.put(sentinel)

                        thread = threading.Thread(target=_run, daemon=True)
                        thread.start()

                        while True:
                            item = await loop.run_in_executor(None, q.get)
                            if item is sentinel:
                                break
                            if isinstance(item, Exception):
                                raise item
                            response_text += item
                            yield f"data: {json.dumps({'type': 'token', 'data': item})}\n\n"

                        context_data = {"type": "general", "llm": "groq", "model": model}
                    else:
                        # Fallback to non-streaming
                        response_text, context_data = await _handle_general_intent(
                            body.message, context, history, user_info, conversation_summary
                        )
                        # Stream word by word
                        for word in response_text.split(" "):
                            yield f"data: {json.dumps({'type': 'token', 'data': word + ' '})}\n\n"
                            await asyncio.sleep(0.02)
                except Exception as exc:
                    logger.error("Streaming LLM failed: %s", exc)
                    response_text, context_data = await _handle_general_intent(
                        body.message, context, history, user_info, conversation_summary
                    )
                    for word in response_text.split(" "):
                        yield f"data: {json.dumps({'type': 'token', 'data': word + ' '})}\n\n"
                        await asyncio.sleep(0.02)
            else:
                # Use structured handler (non-streaming, but fast)
                handler_map = {
                    "user_requests": _handle_user_requests_intent,
                    "low_stock": _handle_low_stock_intent,
                    "resource_requests": _handle_resource_requests_intent,
                    "available_resources": _handle_available_resources_intent,
                    "disaster_status": _handle_disaster_status_intent,
                    "anomalies": _handle_anomalies_intent,
                    "briefing": _handle_briefing_intent,
                    "supply_demand_gap": _handle_supply_demand_gap_intent,
                    "request_lifecycle": _handle_request_lifecycle_intent,
                    "chatbot_activity": _handle_chatbot_activity_intent,
                    "activity_heatmap": _handle_activity_heatmap_intent,
                    "engagement": _handle_engagement_intent,
                    "registration_trends": _handle_registration_trends_intent,
                    "request_pipeline": _handle_request_pipeline_intent,
                    "trends": _handle_trends_intent,
                    "geographic": _handle_geographic_intent,
                    "disaster_comparison": _handle_disaster_comparison_intent,
                    "responder_performance": _handle_responder_performance_intent,
                    "digest": _handle_digest_intent,
                    "users_overview": lambda ctx: _handle_users_overview_intent(ctx, user),
                }
                
                # Causal handler for streaming
                async def _handle_causal_stream(ctx):
                    return await _handle_causal_intent(body.message, ctx)
                
                handler_map["causal"] = _handle_causal_stream

                if intent in handler_map:
                    handler = handler_map[intent]
                    if intent == "users_overview":
                        response_text, context_data = handler(context)
                    else:
                        response_text, context_data = await handler(context)
                elif intent == "allocate_resources":
                    response_text, context_data = await _handle_allocate_resources_intent(body.message, context)
                elif intent == "generate_report":
                    response_text, context_data = await _handle_generate_report_intent(context)
                else:
                    response_text, context_data = await _handle_general_intent(
                        body.message, context, history,
                        {"role": user.get("role"), "name": user.get("name")},
                        conversation_summary,
                    )

                # Stream word by word
                for word in response_text.split(" "):
                    yield f"data: {json.dumps({'type': 'token', 'data': word + ' '})}\n\n"
                    await asyncio.sleep(0.015)

            _add_message_to_session(session_id, "assistant", response_text)

            # Emit context data
            if context_data:
                yield f"data: {json.dumps({'type': 'context_data', 'data': context_data})}\n\n"

            # Generate and emit follow-up suggestions
            user_role = user.get("role", "user")
            follow_up_suggestions = _generate_follow_up_suggestions(intent, context_data, user_role)
            if follow_up_suggestions:
                yield f"data: {json.dumps({'type': 'follow_up', 'suggestions': follow_up_suggestions})}\n\n"

            # Generate and emit action cards
            action_cards = _generate_action_cards(intent, context_data, user_role)
            if action_cards:
                yield f"data: {json.dumps({'type': 'action_cards', 'cards': action_cards})}\n\n"

            # Persist in background
            background_tasks.add_task(_persist_message, session_id, "user", body.message, intent=intent)
            background_tasks.add_task(
                _persist_message, session_id, "assistant", response_text,
                intent=intent, context_data=context_data,
                follow_up_suggestions=follow_up_suggestions, action_cards=action_cards,
            )

            # Done
            yield f"data: {json.dumps({'type': 'done', 'intent': intent, 'session_id': session_id})}\n\n"

        except Exception as exc:
            logger.error("Chat stream error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Action Execution Endpoint ──────────────────────────────────────────────────


@router.post("/actions/execute", response_model=ActionExecuteResponse)
async def execute_action(
    body: ActionExecuteRequest,
    user: dict = Depends(get_current_user),
):
    """
    Execute an action suggested by DisasterGPT.
    Supports: resource allocation, report generation, alert acknowledgment, etc.
    """
    user_role = user.get("role", "")
    if user_role not in ("admin", "coordinator", "super_admin"):
        raise HTTPException(status_code=403, detail="Only admins and coordinators can execute actions")

    logger.info("Action execution user=%s type=%s: %s", user.get("id"), body.action_type, body.action_payload)

    try:
        result = {}
        success = True
        message = ""

        if body.action_type == "allocate_resources":
            # Call the resource allocation endpoint
            disaster_id = body.action_payload.get("disaster_id")
            resource_type = body.action_payload.get("resource_type")
            quantity = body.action_payload.get("quantity_needed", 0)

            if not disaster_id or not resource_type:
                raise HTTPException(status_code=400, detail="disaster_id and resource_type are required")

            # Find available resources
            avail_resp = await db.table("resources").select(
                "id,quantity"
            ).eq("type", resource_type).eq("status", "available").gte("quantity", quantity).limit(1).async_execute()

            if avail_resp.data:
                resource = avail_resp.data[0]
                # Allocate the resource
                await db.table("resources").update({
                    "status": "allocated",
                    "allocated_to": disaster_id,
                }).eq("id", resource["id"]).async_execute()

                result = {"resource_id": resource["id"], "allocated_quantity": quantity, "disaster_id": disaster_id}
                message = f"Successfully allocated {quantity} units of {resource_type} to disaster {disaster_id}"
            else:
                success = False
                message = f"No available {resource_type} with sufficient quantity ({quantity}) found"
                result = {"available": False, "resource_type": resource_type}

        elif body.action_type == "generate_sitrep":
            disaster_id = body.action_payload.get("disaster_id")
            # Trigger sitrep generation
            from app.services.sitrep_service import generate_sitrep

            report = await generate_sitrep(disaster_id=disaster_id)
            result = {"report": report}
            message = "Situation report generated successfully"

        elif body.action_type == "acknowledge_alert":
            alert_id = body.action_payload.get("alert_id")
            if alert_id:
                await db.table("anomaly_alerts").update({
                    "status": "acknowledged",
                    "acknowledged_by": user.get("id"),
                    "acknowledged_at": datetime.now(UTC).isoformat(),
                }).eq("id", alert_id).async_execute()
                result = {"alert_id": alert_id, "status": "acknowledged"}
                message = f"Alert {alert_id} acknowledged"
            else:
                success = False
                message = "alert_id is required"

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action type: {body.action_type}")

        # Log the action
        try:
            await db_admin.table("disastergpt_action_log").insert({
                "session_id": body.session_id,
                "user_id": user.get("id", "unknown"),
                "action_type": body.action_type,
                "action_payload": body.action_payload,
                "result_status": "success" if success else "failed",
                "result_data": result,
            }).async_execute()
        except Exception as exc:
            logger.warning("Failed to log action: %s", exc)

        return ActionExecuteResponse(
            success=success,
            action_type=body.action_type,
            result=result,
            message=message,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Action execution failed: %s", exc, exc_info=True)

        # Log failed action
        try:
            await db_admin.table("disastergpt_action_log").insert({
                "session_id": body.session_id,
                "user_id": user.get("id", "unknown"),
                "action_type": body.action_type,
                "action_payload": body.action_payload,
                "result_status": "failed",
                "result_data": {"error": str(exc)},
            }).async_execute()
        except Exception:
            pass

        raise HTTPException(status_code=500, detail=f"Action execution failed: {exc}")


# ── Digest Subscription Endpoints ──────────────────────────────────────────────


@router.post("/digest/subscribe", response_model=DigestSubscribeResponse)
async def subscribe_digest(
    body: DigestSubscribeRequest,
    user: dict = Depends(get_current_user),
):
    """Subscribe to daily auto-digest briefings."""
    try:
        user_id = user.get("id", "unknown")
        user_role = user.get("role", "unknown")

        # Upsert subscription
        existing = (
            await db_admin.table("disastergpt_digest_subscriptions")
            .select("user_id")
            .eq("user_id", user_id)
            .maybe_single()
            .async_execute()
        )

        if existing.data:
            await db_admin.table("disastergpt_digest_subscriptions").update({
                "digest_time": body.digest_time,
                "timezone": body.timezone,
                "enabled": True,
            }).eq("user_id", user_id).async_execute()
        else:
            await db_admin.table("disastergpt_digest_subscriptions").insert({
                "user_id": user_id,
                "user_role": user_role,
                "digest_time": body.digest_time,
                "timezone": body.timezone,
                "enabled": True,
            }).async_execute()

        # Calculate next digest time
        from datetime import time as _time

        hour, minute = map(int, body.digest_time.split(":"))
        now = datetime.now(UTC)
        next_digest = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_digest <= now:
            next_digest += timedelta(days=1)

        return DigestSubscribeResponse(
            success=True,
            message=f"Subscribed to daily digest at {body.digest_time} {body.timezone}",
            next_digest_at=next_digest.isoformat(),
        )
    except Exception as exc:
        logger.error("Digest subscription failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to subscribe: {exc}")


@router.delete("/digest/unsubscribe")
async def unsubscribe_digest(
    user: dict = Depends(get_current_user),
):
    """Unsubscribe from daily auto-digest briefings."""
    try:
        user_id = user.get("id")
        await db_admin.table("disastergpt_digest_subscriptions").update({
            "enabled": False,
        }).eq("user_id", user_id).async_execute()
        return {"success": True, "message": "Unsubscribed from daily digest"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to unsubscribe: {exc}")


@router.get("/digest/history")
async def get_digest_history(
    limit: int = 10,
    user: dict = Depends(get_current_user),
):
    """Get past digest history."""
    try:
        user_id = user.get("id")
        resp = (
            await db_admin.table("disastergpt_digest_log")
            .select("id, digest_content, sent_at")
            .eq("user_id", user_id)
            .order("sent_at", desc=True)
            .limit(limit)
            .async_execute()
        )
        return resp.data or []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch digest history: {exc}")


# ── Scheduled Digest Runner (called by cron or background task) ────────────────


@router.post("/digest/run")
async def run_scheduled_digests(
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_role("admin")),
):
    """
    Trigger scheduled digest generation for all subscribed users.
    This should be called by a cron job at the configured digest times.
    """
    logger.info("Running scheduled digests triggered by admin=%s", user.get("id"))

    try:
        resp = (
            await db_admin.table("disastergpt_digest_subscriptions")
            .select("user_id, user_role, digest_time, timezone")
            .eq("enabled", True)
            .async_execute()
        )
        subscriptions = resp.data or []

        if not subscriptions:
            return {"message": "No active digest subscriptions", "count": 0}

        # Generate digests in background
        for sub in subscriptions:
            background_tasks.add_task(_generate_and_send_digest, sub)

        return {"message": f"Queued {len(subscriptions)} digest generations", "count": len(subscriptions)}
    except Exception as exc:
        logger.error("Failed to run scheduled digests: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to run digests: {exc}")


async def _generate_and_send_digest(subscription: dict):
    """Generate a digest for a single user and store it."""
    user_id = subscription.get("user_id")
    user_role = subscription.get("user_role", "user")

    try:
        # Build a fake user dict for context pulling
        user = {"id": user_id, "role": user_role}

        # Pull full context
        context = await _get_full_context(user, intent="digest")

        # Generate digest
        digest_text, _ = await _handle_digest_intent(context)

        # Store in digest log
        await db_admin.table("disastergpt_digest_log").insert({
            "user_id": user_id,
            "digest_content": digest_text,
        }).async_execute()

        # Update last_sent_at
        await db_admin.table("disastergpt_digest_subscriptions").update({
            "last_sent_at": datetime.now(UTC).isoformat(),
        }).eq("user_id", user_id).async_execute()

        logger.info("Generated digest for user=%s", user_id)
    except Exception as exc:
        logger.error("Failed to generate digest for user=%s: %s", user_id, exc)


# ── Proactive Anomaly Alert Endpoint ───────────────────────────────────────────


@router.get("/alerts/proactive")
async def get_proactive_alerts(
    user: dict = Depends(get_current_user),
):
    """
    Get proactive anomaly-based insights.
    Analyzes current data for anomalies and returns actionable alerts.
    """
    try:
        context = await _get_full_context(user, intent="briefing")
        alerts = context.get("active_alerts", [])

        # Also check for data-driven anomalies
        proactive_insights = []

        # Check supply-demand gaps
        gaps = context.get("supply_demand_gaps") or {}
        critical = gaps.get("critical_shortages", [])
        for gap in critical[:3]:
            proactive_insights.append({
                "type": "supply_shortage",
                "severity": "critical",
                "title": f"Critical shortage: {gap['type']}",
                "description": f"Only {gap['coverage_pct']}% coverage — {gap['demand']} demanded vs {gap['supply']} available",
                "action_suggestion": f"Allocate {gap['demand'] - gap['supply']} units of {gap['type']}",
            })

        # Check stale requests
        lifecycle = context.get("request_lifecycle") or {}
        stale_count = lifecycle.get("stale_count", 0)
        if stale_count > 0:
            proactive_insights.append({
                "type": "stale_requests",
                "severity": "high" if stale_count > 5 else "medium",
                "title": f"{stale_count} requests pending > 48 hours",
                "description": "These requests need immediate attention to avoid escalation",
                "action_suggestion": "Review and prioritize stale requests",
            })

        # Check chatbot abandonment
        chatbot = context.get("chatbot_intake_activity") or {}
        abandon_rate = chatbot.get("abandonment_rate", 0)
        if abandon_rate > 30:
            proactive_insights.append({
                "type": "high_abandonment",
                "severity": "medium",
                "title": f"High chatbot abandonment rate: {abandon_rate}%",
                "description": "Victims are abandoning the intake process — consider simplifying the flow",
                "action_suggestion": "Review chatbot UX and reduce friction",
            })

        # Check low-engagement roles
        engagement = context.get("engagement_summary") or {}
        if engagement.get("active_volunteers_30d", 0) == 0:
            proactive_insights.append({
                "type": "zero_volunteer_activity",
                "severity": "medium",
                "title": "No active volunteers in the last 30 days",
                "description": "Volunteer engagement has dropped to zero — consider outreach campaigns",
                "action_suggestion": "Send volunteer engagement notifications",
            })

        return {
            "system_alerts": alerts,
            "proactive_insights": proactive_insights,
            "total_alerts": len(alerts) + len(proactive_insights),
            "generated_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        logger.error("Failed to get proactive alerts: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to get proactive alerts: {exc}")


# ── Session Management Endpoints ───────────────────────────────────────────────


@router.get("/sessions/{session_id}", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str = Path(..., description="Session ID to retrieve history for"),
    user: dict = Depends(get_current_user),
):
    """Retrieve conversation history for a specific session (from DB)."""
    # Try DB first
    db_history = await _get_session_history_from_db(session_id, limit=50)
    if db_history:
        return SessionHistoryResponse(
            session_id=session_id,
            messages=[ChatMessage(**m) for m in db_history],
            created_at=db_history[0].get("timestamp", "") if db_history else "",
            message_count=len(db_history),
        )

    # Fall back to in-memory
    if session_id not in _chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _chat_sessions[session_id]
    messages = session.get("messages", [])

    return SessionHistoryResponse(
        session_id=session_id,
        messages=[ChatMessage(**m) for m in messages],
        created_at=session.get("created_at", ""),
        message_count=len(messages),
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str = Path(..., description="Session ID to delete"),
    user: dict = Depends(get_current_user),
):
    """Clear/delete a conversation session (from DB and in-memory)."""
    # Delete from DB
    try:
        await db_admin.table("disastergpt_messages").delete().eq("session_id", session_id).async_execute()
        await db_admin.table("disastergpt_sessions").delete().eq("session_id", session_id).async_execute()
    except Exception as exc:
        logger.warning("Failed to delete session from DB: %s", exc)

    # Delete from in-memory
    if session_id in _chat_sessions:
        del _chat_sessions[session_id]

    return {"message": f"Session {session_id} deleted successfully", "session_id": session_id}