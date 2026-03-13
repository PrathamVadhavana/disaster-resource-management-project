"""
DisasterGPT — LLM Query API Router
====================================
Exposes the RAG-powered LLM assistant as a FastAPI endpoint.

Endpoints
─────────
POST /api/llm/query     – Submit a query and receive a full response
POST /api/llm/stream    – Submit a query and receive a streaming SSE response
POST /api/llm/index     – Trigger knowledge base re-indexing (admin only)
GET  /api/llm/stats     – Knowledge base statistics
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
from fastapi import APIRouter, Depends, HTTPException, Path
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


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    created_at: str
    message_count: int


# ── Lazy singleton ──────────────────────────────────────────────────────────────

_rag_instance = None


def _get_rag():
    """Lazy-load DisasterRAG to avoid import-time heavyweight init."""
    global _rag_instance
    if _rag_instance is None:
        from ml.disaster_rag import DisasterRAG

        _rag_instance = DisasterRAG()
    return _rag_instance


# ── Endpoints ───────────────────────────────────────────────────────────────────


@router.post("/query", response_model=LLMQueryResponse)
async def llm_query(
    body: LLMQueryRequest,
    user: dict = Depends(get_current_user),
):
    """
    Submit a query to DisasterGPT and receive a full response.

    The pipeline:
      1. Embeds the query and retrieves relevant historical documents
      2. Fetches live disaster state from the database
      3. Generates a context-augmented response via the LLM
      4. Returns the response, sources, and a confidence score
    """
    logger.info(
        "LLM query from user=%s: %.80s...",
        user.get("id", "?"),
        body.query,
    )

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
        raise HTTPException(
            status_code=503,
            detail=f"LLM service unavailable: {exc}",
        )
    except Exception as exc:
        logger.error("LLM query failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="LLM query failed")


@router.post("/stream")
async def llm_stream(
    body: LLMQueryRequest,
    user: dict = Depends(get_current_user),
):
    """
    Streaming version — returns server-sent events (SSE).

    Event types:
      - sources: JSON array of retrieved source documents
      - token:   Single generated token
      - done:    Final event with confidence score
    """
    logger.info(
        "LLM stream from user=%s: %.80s...",
        user.get("id", "?"),
        body.query,
    )

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
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.post("/index", response_model=LLMIndexResponse)
async def llm_index(
    user: dict = Depends(require_role("admin")),
):
    """
    Re-index the knowledge base from the database and training data.
    Admin-only endpoint.
    """
    logger.info("Knowledge base re-index triggered by user=%s", user.get("id", "?"))

    try:
        rag = _get_rag()
        kb = rag.knowledge_base

        total_indexed = 0

        # Index disasters from DB
        try:
            resp = await db.table("disasters").select("*").async_execute()
            if resp.data:
                count = kb.index_disasters_from_db(resp.data)
                total_indexed += count
                logger.info("Indexed %d disaster records from DB", count)
        except Exception as exc:
            logger.warning("DB disaster indexing failed: %s", exc)

        # Index situation reports from training data
        from pathlib import Path

        reports_path = Path("training_data/disaster_instructions.jsonl")
        if reports_path.exists():
            count = kb.index_situation_reports(reports_path)
            total_indexed += count
            logger.info("Indexed %d situation reports", count)

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
        return LLMStatsResponse(
            total_documents=rag.knowledge_base.count,
            status="operational",
        )
    except Exception as exc:
        logger.warning("Stats retrieval failed: %s", exc)
        return LLMStatsResponse(
            total_documents=0,
            status=f"degraded: {exc}",
        )


# ── Intent classification ───────────────────────────────────────────────────

import re

_CAUSAL_PATTERNS = re.compile(
    r"\b(what.?if|counterfactual|causal|root.?cause|intervene|intervention|"
    r"would.?have|effect.?of|impact.?of.+on|treatment.?effect|"
    r"reduce.?casualties|reduce.?damage|why.?did|cause.?of)\b",
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
    """Classify query intent into one of: 'causal', 'multi_agent', 'rag'.

    Uses lightweight regex pattern matching on the query text.
    """
    causal_score = len(_CAUSAL_PATTERNS.findall(query))
    agent_score = len(_MULTI_AGENT_PATTERNS.findall(query))

    if causal_score > 0 and causal_score >= agent_score:
        return "causal"
    if agent_score > 0:
        return "multi_agent"
    return "rag"


# ── Unified DisasterGPT endpoint ────────────────────────────────────────────


class UnifiedQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000, description="Natural-language question")
    disaster_id: str | None = Field(None, description="Optional disaster ID for focused context")
    mode: str | None = Field(None, description="Force a mode: 'rag', 'multi_agent', 'causal', or None for auto")
    top_k: int = Field(5, ge=1, le=20)
    max_tokens: int = Field(1024, ge=64, le=4096)
    temperature: float = Field(0.7, ge=0.0, le=2.0)


@router.post("/unified")
async def unified_stream(
    body: UnifiedQueryRequest,
    user: dict = Depends(get_current_user),
):
    """Unified DisasterGPT endpoint — auto-classifies intent and routes to
    the appropriate AI system (RAG, Multi-Agent, or Causal AI).

    Always streams SSE events. Event types:
      - meta:         Classification info & mode
      - sources:      Retrieved documents (RAG mode)
      - token:        Generated text token
      - causal_data:  Causal analysis results (inline data)
      - agent_start:  Agent starting work
      - agent_result: Agent completed
      - done:         Stream complete
      - error:        Something went wrong
    """
    mode = body.mode or _classify_intent(body.query)
    logger.info(
        "Unified query mode=%s user=%s: %.80s...",
        mode,
        user.get("id", "?"),
        body.query,
    )

    async def event_generator():
        # Emit classification metadata
        yield f"data: {json.dumps({'type': 'meta', 'mode': mode, 'query': body.query})}\n\n"

        try:
            if mode == "causal":
                async for chunk in _handle_causal_stream(body):
                    yield f"data: {chunk}\n\n"
            elif mode == "multi_agent":
                async for chunk in _handle_multi_agent_stream(body):
                    yield f"data: {chunk}\n\n"
            else:
                async for chunk in _handle_rag_stream(body):
                    yield f"data: {chunk}\n\n"
        except Exception as exc:
            logger.error("Unified stream error (%s): %s", mode, exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'mode': mode})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _handle_rag_stream(body: UnifiedQueryRequest):
    """Stream RAG response tokens."""
    try:
        rag = _get_rag()
    except Exception as exc:
        logger.warning("RAG init failed, falling back to DB-only response: %s", exc)
        async for chunk in _fallback_db_response(body):
            yield chunk
        return

    try:
        async for chunk in rag.query_stream(
            question=body.query,
            disaster_id=body.disaster_id,
            top_k=body.top_k,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
        ):
            yield chunk
    except Exception as exc:
        logger.warning("RAG stream failed, falling back to DB-only: %s", exc)
        async for chunk in _fallback_db_response(body):
            yield chunk


async def _handle_multi_agent_stream(body: UnifiedQueryRequest):
    """Stream multi-agent coordination results, then synthesise via RAG."""
    from ml.multi_agent import get_multi_agent_system

    system = get_multi_agent_system()
    agent_results: list[dict] = []

    async for chunk in system.process_query_stream(
        query=body.query,
        disaster_id=body.disaster_id,
    ):
        yield chunk
        try:
            parsed = json.loads(chunk)
            if parsed.get("type") == "agent_result":
                agent_results.append(parsed)
        except (json.JSONDecodeError, TypeError):
            pass

    # After agents complete, synthesise a unified narrative via RAG
    try:
        agent_summary = _summarise_agent_results(body.query, agent_results)
        rag = _get_rag()
        async for chunk in rag.query_stream(
            question=agent_summary,
            disaster_id=body.disaster_id,
            top_k=body.top_k,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
        ):
            yield chunk
    except Exception as exc:
        logger.warning("RAG synthesis after agents failed: %s", exc)
        # Emit agent results as formatted text
        _summarise_agent_results(body.query, agent_results)
        yield json.dumps({"type": "token", "data": _format_agent_fallback(agent_results)})


async def _handle_causal_stream(body: UnifiedQueryRequest):
    """Run causal analysis and stream results, then explain via RAG."""
    # Gather causal data
    causal_context_parts: list[str] = []

    try:
        # Get or create causal model
        from app.routers.causal import _get_causal_model
        from ml.causal_model import CAUSAL_EDGES, CAUSAL_NODES, DisasterCausalModel

        cm = await _get_causal_model()

        # 1. Causal effects
        try:
            rt_cas = cm.estimate_response_time_on_casualties()
            ra_dmg = cm.estimate_resource_availability_on_damage()
            effects_data = {
                "type": "causal_data",
                "subtype": "effects",
                "data": [rt_cas.to_dict(), ra_dmg.to_dict()],
            }
            yield json.dumps(effects_data)

            def _fmt_p(p):
                return f"{p:.4f}" if p is not None else "N/A"

            causal_context_parts.append(
                f"Causal Effects:\n"
                f"- Response time -> casualties: ATE={rt_cas.ate:.4f} (p={_fmt_p(rt_cas.p_value)})\n"
                f"- Resource availability -> damage: ATE={ra_dmg.ate:.4f} (p={_fmt_p(ra_dmg.p_value)})"
            )
        except Exception as e:
            logger.warning("Causal effects estimation failed: %s", e)

        # 2. Root causes
        try:
            root_causes = cm.rank_root_causes("casualties")
            causes_data = {
                "type": "causal_data",
                "subtype": "root_causes",
                "data": [
                    {"treatment": rc.treatment, "outcome": rc.outcome, "ate": rc.ate, "p_value": rc.p_value}
                    for rc in root_causes[:5]
                ],
            }
            yield json.dumps(causes_data)
            causal_context_parts.append(
                "Root causes of casualties (ranked by |ATE|):\n"
                + "\n".join(f"- {rc.treatment}: ATE={rc.ate:.4f}" for rc in root_causes[:5])
            )
        except Exception as e:
            logger.warning("Root cause ranking failed: %s", e)

        # 3. If a disaster_id is provided, run counterfactual + top interventions
        if body.disaster_id:
            try:
                result = (
                    await db.table("disasters").select("*").eq("id", body.disaster_id).maybe_single().async_execute()
                )
                disaster = result.data
                if disaster:
                    from app.routers.causal import _disaster_to_observation

                    obs = _disaster_to_observation(disaster)

                    interventions = cm.top_counterfactual_interventions(obs, "casualties", k=3)
                    interventions_data = {
                        "type": "causal_data",
                        "subtype": "interventions",
                        "data": interventions,
                    }
                    yield json.dumps(interventions_data)
                    causal_context_parts.append(
                        f"Top interventions for disaster {body.disaster_id}:\n"
                        + "\n".join(
                            f"- Change {iv['variable']} from {iv['current_value']} to "
                            f"{iv['proposed_value']} → reduces casualties by ~{iv['estimated_reduction']}"
                            for iv in interventions
                        )
                    )
            except Exception as e:
                logger.warning("Counterfactual analysis failed: %s", e)

        # 4. Graph data
        graph_data = {
            "type": "causal_data",
            "subtype": "graph",
            "data": {
                "nodes": CAUSAL_NODES,
                "edges": [{"source": s, "target": t} for s, t in CAUSAL_EDGES],
            },
        }
        yield json.dumps(graph_data)

    except ImportError:
        causal_context_parts.append("Causal model is not available (missing dependencies).")
    except Exception as e:
        logger.error("Causal stream error: %s", e, exc_info=True)
        causal_context_parts.append(f"Causal analysis encountered an error: {e}")

    # 5. Generate narrative explanation using RAG with causal context injected
    causal_context = "\n\n".join(causal_context_parts)
    augmented_query = (
        f"The user asked: {body.query}\n\n"
        f"=== CAUSAL ANALYSIS RESULTS ===\n{causal_context}\n\n"
        f"Using the causal analysis results above, provide a comprehensive answer to the user's question. "
        f"Explain the causal relationships, effect sizes, and any recommended interventions in clear language."
    )

    try:
        rag = _get_rag()
        async for chunk in rag.query_stream(
            question=augmented_query,
            disaster_id=body.disaster_id,
            top_k=body.top_k,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
        ):
            yield chunk
    except Exception as exc:
        logger.warning("RAG synthesis for causal failed: %s", exc)
        # Fallback: emit causal analysis as formatted text
        yield json.dumps(
            {
                "type": "token",
                "data": f"\n\n## Causal Analysis Results\n\n{causal_context}\n",
            }
        )


async def _fallback_db_response(body: UnifiedQueryRequest):
    """Fallback when RAG is unavailable — query the database directly and
    return a formatted summary."""
    parts: list[str] = []
    parts.append(f"## Analysis: {body.query}\n")

    try:
        # Fetch active disasters
        resp = (
            await db.table("disasters").select("id,title,type,severity_score,status,location").limit(20).async_execute()
        )
        disasters = resp.data or []
        if disasters:
            parts.append("### Active Disasters\n")
            parts.append("| # | Title | Type | Severity | Status | Location |")
            parts.append("|---|-------|------|----------|--------|----------|")
            for i, d in enumerate(disasters, 1):
                parts.append(
                    f"| {i} | {d.get('title', 'N/A')} | {d.get('type', 'N/A')} | "
                    f"{d.get('severity_score', 'N/A')} | {d.get('status', 'N/A')} | "
                    f"{d.get('location', 'N/A')} |"
                )
            parts.append("")

            # Basic analysis
            critical = [d for d in disasters if (d.get("severity_score") or 0) >= 7]
            if critical:
                parts.append(f"**{len(critical)} disaster(s) have severity >= 7 and need immediate attention.**\n")
                for d in critical[:5]:
                    parts.append(
                        f"- **{d.get('title', 'Unknown')}** (Severity: {d.get('severity_score', '?')}, Location: {d.get('location', '?')})"
                    )
                parts.append("")
        else:
            parts.append("*No active disasters found in the database.*\n")

        # Fetch open resource requests
        try:
            req_resp = (
                await db.table("resource_requests")
                .select("id,title,status,priority,disaster_id")
                .eq("status", "pending")
                .limit(10)
                .async_execute()
            )
            requests = req_resp.data or []
            if requests:
                parts.append(f"### Pending Resource Requests: {len(requests)}\n")
                for r in requests[:5]:
                    parts.append(f"- {r.get('title', 'Untitled')} (Priority: {r.get('priority', '?')})")
                parts.append("")
        except Exception:
            pass

    except Exception as e:
        parts.append(f"\n*Database query error: {e}*\n")

    parts.append(
        "\n---\n*Note: Running in database-only mode. RAG pipeline is initializing — responses will be richer once ready.*"
    )

    full_text = "\n".join(parts)
    # Stream it as tokens
    for token in full_text.split(" "):
        yield json.dumps({"type": "token", "data": token + " "})


def _format_agent_fallback(agent_results: list[dict]) -> str:
    """Format agent results as markdown when RAG synthesis is unavailable."""
    parts = ["## Multi-Agent Analysis Results\n"]
    agent_icons = {
        "predictor": "🔮",
        "allocator": "📦",
        "analyst": "🔬",
        "responder": "💬",
    }
    for ar in agent_results:
        name = ar.get("agent", "unknown")
        icon = agent_icons.get(name, "🤖")
        data = ar.get("data", {})
        summary = _extract_agent_summary(name, data)
        parts.append(f"### {icon} {name.title()} Agent\n{summary}\n")
    return "\n".join(parts)


def _extract_agent_summary(agent_name: str, data: dict) -> str:
    """Extract a human-readable summary from agent result data."""
    if not isinstance(data, dict):
        return str(data)[:500]
    # Prefer explicit summary/response fields
    if data.get("summary"):
        return data["summary"]
    if data.get("response"):
        return data["response"]
    # Agent-specific formatting
    if agent_name == "predictor":
        sev = data.get("predicted_severity", "unknown")
        conf = data.get("confidence", 0)
        return (
            f"Severity: **{sev}** (confidence: {conf:.0%}). "
            f"Timeline: {data.get('timeline_hours', 'N/A')}h. "
            f"Method: {data.get('method', 'N/A')}."
        )
    if agent_name == "allocator":
        if data.get("allocations"):
            return f"{len(data['allocations'])} resources allocated with {data.get('coverage_pct', 0)}% coverage."
        if data.get("recommended_resources"):
            recs = data["recommended_resources"]
            rec_str = ", ".join(f"{r['type']} (priority {r['priority']})" for r in recs[:4])
            return f"Urgency: {data.get('recommended_urgency', '?')}/10. Resources: {rec_str}."
    if agent_name == "analyst":
        analyses = data.get("analyses", {})
        parts = []
        nlp = analyses.get("nlp", {})
        if nlp:
            parts.append(f"Intent: {nlp.get('query_intent', 'unknown')}.")
            urg = nlp.get("urgency_signals", {})
            if urg.get("is_urgent"):
                parts.append(f"⚠️ Urgent: {', '.join(urg.get('signals', []))}.")
        causal = analyses.get("causal", {})
        if causal.get("insight"):
            parts.append(causal["insight"])
        return " ".join(parts) if parts else "Analysis completed."
    return json.dumps(data, default=str)[:500]


def _summarise_agent_results(query: str, agent_results: list[dict]) -> str:
    """Build an augmented prompt from multi-agent results for RAG synthesis."""
    parts = [f"The user asked: {query}\n\n=== MULTI-AGENT ANALYSIS RESULTS ==="]
    for ar in agent_results:
        agent_name = ar.get("agent", "unknown")
        data = ar.get("data", {})
        summary = _extract_agent_summary(agent_name, data) if isinstance(data, dict) else str(data)[:500]
        parts.append(f"\n[{agent_name.upper()} AGENT]:\n{summary}")

    parts.append(
        "\n\nUsing the multi-agent analysis above, synthesise a comprehensive, "
        "actionable response to the user's question. Include specific recommendations "
        "from each agent's analysis."
    )
    return "\n".join(parts)


# ── Chat Session Management ─────────────────────────────────────────────────────

MAX_HISTORY = 10  # Keep last 10 messages

_chat_sessions: dict[str, dict] = {}  # session_id -> {messages: [], created_at: str}


def _get_or_create_session(session_id: str | None) -> tuple[str, dict]:
    """Get existing session or create new one."""
    if session_id and session_id in _chat_sessions:
        return session_id, _chat_sessions[session_id]
    
    new_id = session_id or str(uuid.uuid4())
    _chat_sessions[new_id] = {
        "messages": [],
        "created_at": datetime.now(UTC).isoformat(),
    }
    return new_id, _chat_sessions[new_id]


def _add_message_to_session(session_id: str, role: str, content: str) -> None:
    """Add a message to session history, keeping only last MAX_HISTORY messages."""
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
    
    # Keep only last MAX_HISTORY messages
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
    """Get resource request summary from live Supabase data (global + last24h)."""
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
    """Get recent individual resource requests across all users (admin/coordinator context)."""
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
            enriched.append(
                {
                    **req,
                    "victim_name": victim.get("full_name"),
                    "victim_email": victim.get("email"),
                    "victim_role": victim.get("role"),
                }
            )
        return enriched
    except Exception as e:
        logger.warning(f"Failed to fetch global individual resource requests: {e}")
        return []


async def _get_inventory_summary() -> dict:
    """Get current resource inventory summary, with fallback to resources table."""
    resources = []
    try:
        resp = await db.table("available_resources").select(
            "id,resource_type,quantity,location,status"
        ).async_execute()
        resources = resp.data or []
    except Exception:
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


async def _get_user_account_snapshot(user_id: str) -> dict:
    """Get core user account data from Supabase users table."""
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
    """Get live platform-wide users snapshot from Supabase users table."""
    try:
        count_resp = await db_admin.table("users").select("id", count="exact").limit(1).async_execute()
        total_users = int(count_resp.count or 0)

        list_limit = min(max(limit, 1), 1000)
        list_fields = "id,full_name,role,created_at"
        if include_pii:
            list_fields = "id,full_name,email,role,created_at"

        users_resp = (
            await db_admin.table("users")
            .select(list_fields)
            .order("created_at", desc=True)
            .limit(list_limit)
            .async_execute()
        )
        users = users_resp.data or []

        by_role: dict[str, int] = {}
        known_roles = ["admin", "victim", "ngo", "donor", "volunteer", "coordinator", "super_admin"]
        for role in known_roles:
            role_resp = (
                await db_admin.table("users")
                .select("id", count="exact")
                .eq("role", role)
                .limit(1)
                .async_execute()
            )
            role_count = int(role_resp.count or 0)
            if role_count > 0:
                by_role[role] = role_count

        # Unknown / null roles
        known_total = sum(by_role.values())
        if total_users > known_total:
            by_role["unknown"] = total_users - known_total

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
    """Get detailed snapshot for a specific disaster when provided."""
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


async def _get_full_context(user: dict, disaster_id: str | None = None) -> dict:
    """Pull all relevant context from Supabase, including user-specific data."""
    context: dict = {}
    user_id = user.get("id")
    user_role = user.get("role", "")

    # ── System-wide data ──────────────────────────────────────────────────────
    context["active_disasters"] = await _get_active_disasters()
    context["resource_requests_summary"] = await _get_resource_requests_summary()
    context["inventory_summary"] = await _get_inventory_summary()
    context["active_alerts"] = await _get_active_alerts()

    elevated_roles = {"admin", "coordinator", "super_admin"}
    user_role_normalized = str(user_role or "").lower()
    include_pii = user_role_normalized in elevated_roles
    context["platform_users"] = await _get_global_users_snapshot(include_pii=include_pii, limit=250)
    if include_pii:
        context["global_resource_requests"] = await _get_global_resource_requests(limit=300)

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

        try:
            vd = await db.table("victim_details").select(
                "current_status,needs,medical_needs"
            ).eq("id", user_id).maybe_single().async_execute()
            context["victim_profile"] = vd.data or {}
        except Exception as e:
            logger.warning(f"victim_details fetch failed: {e}")

    elif user_role == "ngo":
        try:
            ar = await db.table("resource_requests").select(
                "id,resource_type,status,priority,address_text,description"
            ).eq("assigned_to", user_id).in_("status", ["assigned", "in_progress"]).limit(20).async_execute()
            context["assigned_requests"] = ar.data or []
        except Exception as e:
            logger.warning(f"NGO assigned_requests fetch failed: {e}")

        try:
            inv = await db.table("available_resources").select(
                "resource_type,quantity,status"
            ).eq("provider_id", user_id).async_execute()
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

        try:
            vp = await db.table("volunteer_details").select(
                "skills,availability_status,certifications"
            ).eq("id", user_id).maybe_single().async_execute()
            context["volunteer_profile"] = vp.data or {}
        except Exception as e:
            logger.warning(f"volunteer_details fetch failed: {e}")

    elif user_role == "donor":
        try:
            dp = await db.table("donor_pledges").select(
                "id,resource_type,quantity_pledged,status,created_at"
            ).eq("donor_id", user_id).order("created_at", desc=True).limit(10).async_execute()
            context["donor_pledges"] = dp.data or []
        except Exception as e:
            logger.warning(f"donor_pledges fetch failed: {e}")

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
        if focused.get("description"):
            parts.append(f"- Description: {str(focused.get('description'))[:500]}")

    # Active disasters
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

    # Resource requests summary
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

    # Inventory
    inv = context.get("inventory_summary", {})
    parts.append(f"\n## Resource Inventory: {inv.get('total_resources', 0)} total entries")
    for rtype, data in (inv.get("by_type") or {}).items():
        qty = data.get("total_quantity", 0)
        flag = " ⚠️ LOW STOCK" if qty < 50 else ""
        parts.append(f"  - {rtype}: {qty} units{flag}")

    # Alerts
    alerts = context.get("active_alerts", [])
    if alerts:
        parts.append(f"\n## Active Anomaly Alerts ({len(alerts)}):")
        for a in alerts:
            parts.append(f"  - [{a.get('severity','?').upper()}] {a.get('alert_type','?')}: {a.get('description','')}")
    else:
        parts.append("\n## Active Anomaly Alerts: None")

    # ── Personal user data ─────────────────────────────────────────────────
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

    if context.get("ngo_inventory"):
        parts.append(f"\n## This NGO's Inventory ({len(context['ngo_inventory'])} items)")

    if context.get("volunteer_assignments"):
        parts.append(f"\n## This Volunteer's Active Assignments: {len(context['volunteer_assignments'])}")

    if context.get("volunteer_profile"):
        vp = context["volunteer_profile"]
        parts.append(f"  Skills: {', '.join(vp.get('skills') or [])} | Status: {vp.get('availability_status','?')}")

    if context.get("donor_pledges"):
        parts.append(f"\n## This Donor's Recent Pledges ({len(context['donor_pledges'])}):")
        for p in context["donor_pledges"][:3]:
            parts.append(f"  - {p.get('resource_type','?')}: {p.get('quantity_pledged','?')} units ({p.get('status','?')})")

    parts.append("\n=== END OF LIVE DATA ===")
    parts.append("If data is missing or incomplete, say so clearly. Do not invent numbers.")

    return "\n".join(parts)


# ── Intent Detection ───────────────────────────────────────────────────────────


def _detect_intent(message: str) -> str:
    """Detect intent category from user message."""
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

    return "general"


# ── Intent Handlers ───────────────────────────────────────────────────────────


async def _handle_resource_requests_intent(context: dict) -> tuple[str, dict]:
    """Handle 'how many requests' intent."""
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
                f"x{req.get('quantity', 1)} | "
                f"Priority: {req.get('priority', '?')} | "
                f"Victim: {req.get('victim_name') or req.get('victim_id', '?')}"
                + (f" ({req.get('victim_email')})" if req.get('victim_email') else "")
                + (f" | Address: {req.get('address_text')}" if req.get('address_text') else "")
                + "\n"
            )
    
    return "".join(parts), {"type": "resource_requests", "data": summary, "individual_count": len(global_requests)}


async def _handle_available_resources_intent(context: dict) -> tuple[str, dict]:
    """Handle 'what resources are available' intent."""
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
    """Handle 'disaster status' intent."""
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
    """Handle 'allocate resources' intent - call the allocation endpoint."""
    # Parse potential resource allocation from message
    # For now, return a message that describes how to use the allocation endpoint
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
    """Handle 'generate report' intent - call the sitrep generation endpoint."""
    disasters = context.get("active_disasters", [])
    
    parts = ["## Situation Report (SITREP)\n"]
    parts.append("To generate a full situation report, use the `/api/nlp/sitrep/generate` endpoint.\n\n")
    
    # Provide a quick summary
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
    """Handle 'anomalies' intent."""
    alerts = context.get("active_alerts", [])
    
    parts = ["## Active Anomaly Alerts\n"]
    
    if alerts:
        parts.append(f"**Total Active Alerts:** {len(alerts)}\n\n")
        
        # Group by severity
        critical = [a for a in alerts if a.get("severity") == "critical"]
        high = [a for a in alerts if a.get("severity") == "high"]
        medium = [a for a in alerts if a.get("severity") == "medium"]
        low = [a for a in alerts if a.get("severity") == "low"]
        
        if critical:
            parts.append("### 🔴 Critical\n")
            for a in critical:
                parts.append(f"- **{a.get('alert_type', 'Unknown')}**: {a.get('description', 'No description')}\n")
            parts.append("\n")
        
        if high:
            parts.append("### 🟠 High\n")
            for a in high:
                parts.append(f"- **{a.get('alert_type', 'Unknown')}**: {a.get('description', 'No description')}\n")
            parts.append("\n")
        
        if medium:
            parts.append("### 🟡 Medium\n")
            for a in medium:
                parts.append(f"- **{a.get('alert_type', 'Unknown')}**: {a.get('description', 'No description')}\n")
            parts.append("\n")
        
        if low:
            parts.append("### 🟢 Low\n")
            for a in low:
                parts.append(f"- **{a.get('alert_type', 'Unknown')}**: {a.get('description', 'No description')}\n")
    else:
        parts.append("No active anomaly alerts.\n")
    
    return "".join(parts), {"type": "anomalies", "data": {"alerts": alerts}}


async def _handle_users_overview_intent(context: dict, user: dict) -> tuple[str, dict]:
    """Handle user/account overview queries using live Supabase users table snapshot."""
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
        parts.append("\n_PII is hidden for your role; showing aggregate and non-sensitive account data only._\n")

    return "".join(parts), {
        "type": "users_overview",
        "data": {
            "total": total,
            "by_role": by_role,
            "returned": len(users),
            "pii_included": pii_included,
            "requester_role": user.get("role"),
        },
    }


async def _handle_user_requests_intent(context: dict) -> tuple[str, dict]:
    """Show the current user's own resource requests."""
    requests = context.get("user_requests", [])
    if not requests:
        return (
            "You have no resource requests on file in the system. "
            "You can submit a new request from the Requests section of your dashboard.",
            {"type": "user_requests", "count": 0},
        )
    STATUS_EMOJI = {
        "pending": "⏳", "approved": "✅", "assigned": "👷",
        "in_progress": "🔄", "delivered": "📦", "completed": "✅",
        "rejected": "❌", "closed": "🔒",
    }
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
    """Report on resources that are running low."""
    inv = context.get("inventory_summary", {})
    low_types = inv.get("low_stock", [])
    by_type = inv.get("by_type", {})

    if not low_types:
        return (
            "✅ All tracked resource types currently have adequate stock levels (≥ 50 units each).",
            {"type": "low_stock", "count": 0},
        )
    parts = [f"## ⚠️ Low Stock Alert — {len(low_types)} resource type(s) below threshold\n"]
    for rtype in sorted(low_types, key=lambda r: by_type.get(r, {}).get("total_quantity", 0)):
        qty = by_type.get(rtype, {}).get("total_quantity", 0)
        locs = by_type.get(rtype, {}).get("count", 0)
        parts.append(f"- **{rtype}**: {qty} units across {locs} location(s) — **restock needed**")
    parts.append("\nConsider issuing a procurement request or reallocating from lower-severity zones.")
    return "\n".join(parts), {"type": "low_stock", "items": low_types}


async def _handle_general_intent(
    message: str,
    context: dict,
    history: list[dict],
    user_info: dict | None = None,
) -> tuple[str, dict]:
    """Handle general questions using Groq with injected live Supabase context."""
    try:
        from groq import Groq
    except ImportError:
        logger.error("groq package not installed. Run: pip install groq")
        return _format_context_as_system_prompt(context, user_info), {"fallback": "no_groq_package"}

    system_prompt = _format_context_as_system_prompt(context, user_info)

    messages = []
    for msg in history[-6:]:  # last 3 turns of conversation
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
            "I can see the live disaster data but my AI response engine is not configured "
            "(GROQ_API_KEY missing). Please contact your administrator.",
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
        # Graceful degradation: show a useful plain-text summary
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
        if context.get("user_requests"):
            fallback_msg += f"\n**Your requests:** {len(context['user_requests'])} on file\n"
        fallback_msg += "\n*AI response engine temporarily unavailable. Showing raw data summary.*"
        return fallback_msg, {"type": "general", "fallback": "api_error", "error": str(e)}


# ── Chat Endpoints ──────────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """
    Chat with DisasterGPT.
    Pulls real-time data from Supabase, detects user intent, and responds
    using role-specific context + Groq for general questions.
    """
    logger.info(
        "Chat request user=%s role=%s session=%s: %.80s...",
        user.get("id", "?"),
        user.get("role", "?"),
        body.session_id or "new",
        body.message,
    )

    # Merge JWT user with any frontend-provided hints (role may be missing from JWT)
    if body.user_context:
        if body.user_context.role and not user.get("role"):
            user["role"] = body.user_context.role
        if body.user_context.name:
            user["name"] = body.user_context.name
        if body.user_context.user_id and not user.get("id"):
            user["id"] = body.user_context.user_id

    # Session management
    session_id, session_data = _get_or_create_session(body.session_id)
    history = session_data.get("messages", [])
    _add_message_to_session(session_id, "user", body.message)

    # Pull live Supabase context
    disaster_id = body.context.disaster_id if body.context else None
    context = await _get_full_context(user, disaster_id)

    # Detect intent and route
    intent = _detect_intent(body.message)
    logger.info("Detected intent=%s for user=%s role=%s", intent, user.get("id", "?"), user.get("role", "?"))

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
        else:
            user_info = {
                "role": user.get("role"),
                "name": user.get("name"),
                "user_requests": context.get("user_requests", []),
            }
            response_text, context_data = await _handle_general_intent(
                body.message, context, history, user_info
            )

        if force_live_llm and intent != "general":
            user_info = {
                "role": user.get("role"),
                "name": user.get("name"),
                "user_requests": context.get("user_requests", []),
            }
            response_text, context_data = await _handle_general_intent(
                body.message, context, history, user_info
            )
            if isinstance(context_data, dict):
                context_data["intent_routed"] = intent
                context_data["mode"] = "forced_live_llm"
    except Exception as e:
        logger.error(f"Error handling intent {intent}: {e}", exc_info=True)
        response_text = (
            f"I encountered an error while processing your request. "
            f"Error: {str(e)[:200]}"
        )
        context_data = {"error": str(e), "intent": intent}

    _add_message_to_session(session_id, "assistant", response_text)

    return ChatResponse(
        message=response_text,
        session_id=session_id,
        intent=intent,
        context_data=context_data,
    )


@router.get("/sessions/{session_id}", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str = Path(..., description="Session ID to retrieve history for"),
    user: dict = Depends(get_current_user),
):
    """
    Retrieve conversation history for a specific session.
    Returns the last 10 messages.
    """
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
    """
    Clear/delete a conversation session.
    """
    if session_id not in _chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del _chat_sessions[session_id]
    
    return {"message": f"Session {session_id} deleted successfully", "session_id": session_id}
