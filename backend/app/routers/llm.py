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

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.database import db
from app.dependencies import get_current_user, require_role

logger = logging.getLogger("llm_router")

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────────────────

class LLMQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Natural-language question")
    disaster_id: Optional[str] = Field(None, description="Optional disaster ID for focused context")
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
    disaster_id: Optional[str] = None
    documents_retrieved: int = 0


class LLMStatsResponse(BaseModel):
    total_documents: int
    status: str


class LLMIndexResponse(BaseModel):
    indexed: int
    total: int
    message: str


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
        user.get("id", "?"), body.query,
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
        user.get("id", "?"), body.query,
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
    disaster_id: Optional[str] = Field(None, description="Optional disaster ID for focused context")
    mode: Optional[str] = Field(None, description="Force a mode: 'rag', 'multi_agent', 'causal', or None for auto")
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
        mode, user.get("id", "?"), body.query,
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
        summary = _summarise_agent_results(body.query, agent_results)
        yield json.dumps({"type": "token", "data": _format_agent_fallback(agent_results)})


async def _handle_causal_stream(body: UnifiedQueryRequest):
    """Run causal analysis and stream results, then explain via RAG."""
    # Gather causal data
    causal_context_parts: list[str] = []

    try:
        from ml.causal_model import DisasterCausalModel, CAUSAL_NODES, CAUSAL_EDGES

        # Get or create causal model
        from app.routers.causal import _get_causal_model
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
                    {"treatment": rc.treatment, "outcome": rc.outcome,
                     "ate": rc.ate, "p_value": rc.p_value}
                    for rc in root_causes[:5]
                ],
            }
            yield json.dumps(causes_data)
            causal_context_parts.append(
                "Root causes of casualties (ranked by |ATE|):\n" +
                "\n".join(f"- {rc.treatment}: ATE={rc.ate:.4f}" for rc in root_causes[:5])
            )
        except Exception as e:
            logger.warning("Root cause ranking failed: %s", e)

        # 3. If a disaster_id is provided, run counterfactual + top interventions
        if body.disaster_id:
            try:
                result = (
                    await db.table("disasters")
                    .select("*")
                    .eq("id", body.disaster_id)
                    .maybe_single()
                    .async_execute()
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
                        f"Top interventions for disaster {body.disaster_id}:\n" +
                        "\n".join(
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
        yield json.dumps({
            "type": "token",
            "data": f"\n\n## Causal Analysis Results\n\n{causal_context}\n",
        })


async def _fallback_db_response(body: UnifiedQueryRequest):
    """Fallback when RAG is unavailable — query the database directly and
    return a formatted summary."""
    parts: list[str] = []
    parts.append(f"## Analysis: {body.query}\n")

    try:
        # Fetch active disasters
        resp = await db.table("disasters").select("id,title,type,severity_score,status,location").limit(20).async_execute()
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
            critical = [d for d in disasters if (d.get('severity_score') or 0) >= 7]
            if critical:
                parts.append(f"**{len(critical)} disaster(s) have severity >= 7 and need immediate attention.**\n")
                for d in critical[:5]:
                    parts.append(f"- **{d.get('title', 'Unknown')}** (Severity: {d.get('severity_score', '?')}, Location: {d.get('location', '?')})")
                parts.append("")
        else:
            parts.append("*No active disasters found in the database.*\n")

        # Fetch open resource requests
        try:
            req_resp = await db.table("resource_requests").select("id,title,status,priority,disaster_id").eq("status", "pending").limit(10).async_execute()
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

    parts.append("\n---\n*Note: Running in database-only mode. RAG pipeline is initializing — responses will be richer once ready.*")

    full_text = "\n".join(parts)
    # Stream it as tokens
    for token in full_text.split(" "):
        yield json.dumps({"type": "token", "data": token + " "})


def _format_agent_fallback(agent_results: list[dict]) -> str:
    """Format agent results as markdown when RAG synthesis is unavailable."""
    parts = ["## Multi-Agent Analysis Results\n"]
    agent_icons = {
        "predictor": "🔮", "allocator": "📦",
        "analyst": "🔬", "responder": "💬",
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
        return (f"Severity: **{sev}** (confidence: {conf:.0%}). "
                f"Timeline: {data.get('timeline_hours', 'N/A')}h. "
                f"Method: {data.get('method', 'N/A')}.")
    if agent_name == "allocator":
        if data.get("allocations"):
            return (f"{len(data['allocations'])} resources allocated "
                    f"with {data.get('coverage_pct', 0)}% coverage.")
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
