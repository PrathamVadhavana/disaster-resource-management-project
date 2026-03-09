"""
Phase 5 - Natural Language Query Service.

Provides a 'Chat with your data' interface using BOTH:
1. Rule-based keyword matching for DB queries (fast, free)
2. Groq / HuggingFace Inference API for intelligent response generation (free tier)

Falls back to rule-based formatting if no API key is configured.
"""

import json
import time
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.database import db_admin
from app.core.phase5_config import phase5_config

logger = logging.getLogger("nl_query_service")

# LLM State — prefer Groq (free, fast, 70B) over HuggingFace
_llm_available = False
_llm_client = None
_llm_model = ""
_llm_provider = "rule-based"

# Try Groq first (free tier, Llama 3.3 70B)
_groq_api_key = os.getenv("GROQ_API_KEY", "")
if _groq_api_key:
    try:
        from groq import Groq
        _llm_client = Groq(api_key=_groq_api_key)
        _llm_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        _llm_provider = "groq"
        _llm_available = True
        logger.info("Groq API configured (model: %s)", _llm_model)
    except ImportError:
        logger.warning("groq package not installed — trying HuggingFace")
    except Exception as e:
        logger.warning(f"Groq setup failed: {e} — trying HuggingFace")

# Fall back to HuggingFace
if not _llm_available:
    try:
        from huggingface_hub import InferenceClient
        _hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY") or None
        _llm_client = InferenceClient(token=_hf_token)
        _llm_model = os.getenv("HF_MODEL", "HuggingFaceH4/zephyr-7b-beta")
        _llm_provider = "huggingface"
        _llm_available = True
        logger.info("HuggingFace Inference API configured (model: %s)", _llm_model)
    except ImportError:
        logger.warning("huggingface_hub not installed — using rule-based NL query mode")
    except Exception as e:
        logger.warning(f"HuggingFace setup failed: {e} — using rule-based NL query mode")


class NLQueryService:
    """Natural language query interface with optional Groq/HuggingFace LLM enhancement."""

    def __init__(self):
        self.model = _llm_model if _llm_available else "rule-based"

    # -- Tool execution (same DB queries as before) --

    async def _tool_query_disasters(self, params: Dict) -> Any:
        query = db_admin.table("disasters").select("*")
        if params.get("status"): query = query.eq("status", params["status"])
        if params.get("severity"): query = query.eq("severity", params["severity"])
        if params.get("disaster_type"): query = query.eq("type", params["disaster_type"])
        query = query.order("created_at", desc=True).limit(params.get("limit", 20))
        return (await query.async_execute()).data or []

    async def _tool_query_resources(self, params: Dict) -> Any:
        query = db_admin.table("resources").select("*")
        if params.get("status"): query = query.eq("status", params["status"])
        if params.get("resource_type"): query = query.eq("type", params["resource_type"])
        if params.get("disaster_id"): query = query.eq("disaster_id", params["disaster_id"])
        query = query.limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    async def _tool_query_victim_requests(self, params: Dict) -> Any:
        query = db_admin.table("resource_requests").select("*")
        if params.get("status"): query = query.eq("status", params["status"])
        if params.get("priority"): query = query.eq("priority", params["priority"])
        if params.get("resource_type"): query = query.eq("resource_type", params["resource_type"])
        query = query.order("created_at", desc=True).limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    async def _tool_query_predictions(self, params: Dict) -> Any:
        query = db_admin.table("predictions").select("*")
        if params.get("prediction_type"): query = query.eq("prediction_type", params["prediction_type"])
        if params.get("since_hours"):
            since = (datetime.utcnow() - timedelta(hours=params["since_hours"])).isoformat()
            query = query.gte("created_at", since)
        if params.get("min_confidence"): query = query.gte("confidence_score", params["min_confidence"])
        query = query.order("created_at", desc=True).limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    async def _tool_query_resource_utilization(self, params: Dict) -> Any:
        resp = await db_admin.table("resources").select("id, type, status, quantity").async_execute()
        resources = resp.data or []
        total = len(resources)
        by_status = {}; by_type = {}; total_quantity_by_type = {}
        for r in resources:
            status = r.get("status", "unknown"); rtype = r.get("type", "other"); qty = r.get("quantity", 0)
            by_status[status] = by_status.get(status, 0) + 1
            by_type[rtype] = by_type.get(rtype, 0) + 1
            total_quantity_by_type[rtype] = total_quantity_by_type.get(rtype, 0) + qty
        allocated = by_status.get("allocated", 0) + by_status.get("deployed", 0) + by_status.get("in_transit", 0)
        utilization_pct = round(allocated / total * 100, 1) if total > 0 else 0
        return {"total_resources": total, "utilization_pct": utilization_pct, "by_status": by_status, "by_type": by_type, "total_quantity_by_type": total_quantity_by_type}

    async def _tool_query_anomaly_alerts(self, params: Dict) -> Any:
        query = db_admin.table("anomaly_alerts").select("*")
        if params.get("status"): query = query.eq("status", params["status"])
        if params.get("severity"): query = query.eq("severity", params["severity"])
        if params.get("anomaly_type"): query = query.eq("anomaly_type", params["anomaly_type"])
        query = query.order("detected_at", desc=True).limit(params.get("limit", 20))
        return (await query.async_execute()).data or []

    async def _tool_query_ingested_events(self, params: Dict) -> Any:
        from app.services.ingestion import memory_store
        since = None
        if params.get("since_hours"):
            since = (datetime.utcnow() - timedelta(hours=params["since_hours"])).isoformat()
        return memory_store.query_ingested_events(
            event_type=params.get("event_type"),
            since=since,
            limit=params.get("limit", 50),
        )

    async def _tool_query_outcome_tracking(self, params: Dict) -> Any:
        query = db_admin.table("outcome_tracking").select("*")
        if params.get("prediction_type"): query = query.eq("prediction_type", params["prediction_type"])
        query = query.order("created_at", desc=True).limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    async def _tool_query_available_resources(self, params: Dict) -> Any:
        query = db_admin.table("available_resources").select("*").eq("is_active", True)
        if params.get("category"): query = query.eq("category", params["category"])
        query = query.order("category").limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    async def _tool_query_users(self, params: Dict) -> Any:
        query = db_admin.table("users").select("id, full_name, email, role, created_at")
        if params.get("role"): query = query.eq("role", params["role"])
        query = query.order("created_at", desc=True).limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    # -- Rule-based query classification and routing --

    def _classify_and_route(self, query: str) -> Dict[str, Any]:
        """Parse the NL query using keyword matching and return the tool + params to call."""
        q = query.lower().strip()
        params = {}

        # Severity filters
        for sev in ["critical", "high", "medium", "low"]:
            if sev in q:
                params["severity"] = sev
                break

        # Status filters
        for st in ["active", "monitoring", "resolved", "pending", "approved", "assigned"]:
            if st in q:
                params["status"] = st
                break

        # Disaster type filters
        for dt in ["earthquake", "flood", "hurricane", "tornado", "wildfire", "tsunami", "drought", "landslide", "volcano"]:
            if dt in q:
                params["disaster_type"] = dt
                break

        # Priority filters
        for pri in ["critical", "high", "medium", "low"]:
            if f"{pri} priority" in q or f"priority {pri}" in q:
                params["priority"] = pri
                break

        # Route to the right tool based on keywords
        if any(w in q for w in ["anomal", "unusual", "spike", "unexpected", "weird"]):
            return {"tool": "anomaly_alerts", "params": params, "category": "anomalies"}
        if any(w in q for w in ["predict", "forecast", "ml ", "model", "confidence"]):
            params.setdefault("since_hours", 48)
            return {"tool": "predictions", "params": params, "category": "predictions"}
        if any(w in q for w in ["outcome", "accuracy", "actual vs", "performance"]):
            return {"tool": "outcome_tracking", "params": params, "category": "outcomes"}
        if any(w in q for w in ["utiliz", "allocation", "how much resource", "resource status"]):
            return {"tool": "resource_utilization", "params": params, "category": "utilization"}
        if any(w in q for w in ["available resource", "inventory", "stock", "supply available", "what's available", "remaining"]):
            for cat in ["food", "water", "medical", "shelter", "clothing", "clothes"]:
                if cat in q:
                    params["category"] = cat.capitalize()
                    break
            return {"tool": "available_resources", "params": params, "category": "available_resources"}
        if any(w in q for w in ["resource", "supply", "supplie"]):
            for rt in ["food", "water", "medical", "shelter", "clothing"]:
                if rt in q:
                    params["resource_type"] = rt
                    break
            return {"tool": "resources", "params": params, "category": "resources"}
        if any(w in q for w in ["request", "victim", "need", "demand", "pending request", "unmet"]):
            return {"tool": "victim_requests", "params": params, "category": "requests"}
        if any(w in q for w in ["user", "volunteer", "ngo", "donor", "admin", "how many user", "team"]):
            for role in ["victim", "ngo", "donor", "volunteer", "admin"]:
                if role in q:
                    params["role"] = role
                    break
            return {"tool": "users", "params": params, "category": "users"}
        if any(w in q for w in ["ingest", "feed", "external", "weather", "gdacs", "usgs", "firms", "social"]):
            for et in ["weather_update", "gdacs_alert", "earthquake", "fire_hotspot", "social_sos"]:
                if et.replace("_", " ") in q or et in q:
                    params["event_type"] = et
                    break
            params.setdefault("since_hours", 24)
            return {"tool": "ingested_events", "params": params, "category": "ingestion"}
        # Default: disasters
        return {"tool": "disasters", "params": params, "category": "disasters"}

    def _format_response(self, category: str, data: Any, query: str) -> str:
        """Format the DB results into a readable markdown response."""
        if isinstance(data, dict):
            # Resource utilization
            if "utilization_pct" in data:
                lines = ["## Resource Utilization\n"]
                lines.append(f"- **Total Resources:** {data.get('total_resources', 0)}")
                lines.append(f"- **Utilization:** {data.get('utilization_pct', 0)}%\n")
                by_status = data.get("by_status", {})
                if by_status:
                    lines.append("| Status | Count |"); lines.append("|--------|-------|")
                    for s, c in sorted(by_status.items()):
                        lines.append(f"| {s} | {c} |")
                by_type = data.get("total_quantity_by_type", data.get("by_type", {}))
                if by_type:
                    lines.append("\n**By Type:**")
                    for t, q in sorted(by_type.items()):
                        lines.append(f"- {t}: {q}")
                return "\n".join(lines)
            return f"`json\n{json.dumps(data, indent=2, default=str)}\n`"

        if not isinstance(data, list) or len(data) == 0:
            return f"No results found for your query: *{query}*"

        count = len(data)

        if category == "disasters":
            lines = [f"## Disasters ({count} found)\n"]
            for d in data[:10]:
                sev = d.get("severity", "?").upper()
                lines.append(f"- **{d.get('title', 'Untitled')}** [{sev}] - {d.get('type', '?')} - Status: {d.get('status', '?')}")
                if d.get("casualties"): lines.append(f"  - Casualties: {d['casualties']:,}")
                if d.get("affected_population"): lines.append(f"  - Affected: {d['affected_population']:,}")
            return "\n".join(lines)

        if category == "resources":
            lines = [f"## Resources ({count} found)\n"]
            lines.append("| Type | Status | Quantity |")
            lines.append("|------|--------|----------|")
            for r in data[:20]:
                lines.append(f"| {r.get('type', '?')} | {r.get('status', '?')} | {r.get('quantity', 0)} |")
            return "\n".join(lines)

        if category == "available_resources":
            lines = [f"## Available Resources ({count} found)\n"]
            lines.append("| Category | Title | Available | Unit |")
            lines.append("|----------|-------|-----------|------|")
            for r in data[:20]:
                total = r.get("total_quantity", 0) or 0
                claimed = r.get("claimed_quantity", 0) or 0
                remaining = max(0, total - claimed)
                lines.append(f"| {r.get('category', '?')} | {r.get('title', '?')} | {remaining}/{total} | {r.get('unit', 'units')} |")
            return "\n".join(lines)

        if category == "requests":
            lines = [f"## Victim Requests ({count} found)\n"]
            lines.append("| Resource | Priority | Status | Qty |")
            lines.append("|----------|----------|--------|-----|")
            for r in data[:20]:
                lines.append(f"| {r.get('resource_type', '?')} | {r.get('priority', '?')} | {r.get('status', '?')} | {r.get('quantity', 1)} |")
            return "\n".join(lines)

        if category == "predictions":
            lines = [f"## Predictions ({count} found)\n"]
            lines.append("| Type | Severity | Confidence | Created |")
            lines.append("|------|----------|------------|---------|")
            for p in data[:15]:
                conf = p.get("confidence_score", 0)
                conf_str = f"{conf:.1%}" if isinstance(conf, (int, float)) else str(conf)
                lines.append(f"| {p.get('prediction_type', '?')} | {p.get('predicted_severity', '-')} | {conf_str} | {str(p.get('created_at', ''))[:16]} |")
            return "\n".join(lines)

        if category == "anomalies":
            lines = [f"## Anomaly Alerts ({count} found)\n"]
            for a in data[:10]:
                lines.append(f"- **[{a.get('severity', '?').upper()}]** {a.get('title', 'Unknown')} ({a.get('anomaly_type', '')})")
                if a.get("ai_explanation"): lines.append(f"  > {a['ai_explanation'][:200]}")
            return "\n".join(lines)

        if category == "ingestion":
            lines = [f"## Ingested Events ({count} found)\n"]
            lines.append("| Type | Title | Severity | Processed |")
            lines.append("|------|-------|----------|-----------|")
            for e in data[:20]:
                title_short = (e.get("title") or "")[:50]
                lines.append(f"| {e.get('event_type', '?')} | {title_short} | {e.get('severity', '?')} | {'Yes' if e.get('processed') else 'No'} |")
            return "\n".join(lines)

        if category == "outcomes":
            lines = [f"## Outcome Tracking ({count} found)\n"]
            for o in data[:10]:
                lines.append(f"- **{o.get('prediction_type', '?')}**: predicted={o.get('predicted_severity', '?')} actual={o.get('actual_severity', '?')} match={o.get('severity_match', '?')}")
            return "\n".join(lines)

        if category == "users":
            lines = [f"## Users ({count} found)\n"]
            lines.append("| Name | Email | Role | Joined |")
            lines.append("|------|-------|------|--------|")
            for u in data[:20]:
                lines.append(f"| {u.get('full_name', '?')} | {u.get('email', '?')} | {u.get('role', '?')} | {str(u.get('created_at', ''))[:10]} |")
            return "\n".join(lines)

        # Fallback: just dump JSON
        return f"Found {count} result(s):\n`json\n{json.dumps(data[:5], indent=2, default=str)}\n`"

    # -- HuggingFace LLM Enhancement --

    async def _generate_llm_response(self, query: str, category: str, data: Any, rule_based_text: str) -> str:
        """Use Groq or HuggingFace API to generate a more intelligent, natural response."""
        if not _llm_available or not _llm_client:
            return rule_based_text

        try:
            import asyncio

            # Prepare data summary (limit size for token efficiency)
            data_summary = ""
            if isinstance(data, dict):
                data_summary = json.dumps(data, indent=2, default=str)[:3000]
            elif isinstance(data, list):
                data_summary = json.dumps(data[:10], indent=2, default=str)[:3000]
            else:
                data_summary = str(data)[:1000]

            system_prompt = """You are the AI assistant for HopeInChaos, a disaster resource management platform. 
You answer questions about the platform's data: disasters, resources, victim requests, predictions, anomalies, and users.
Always base your answers on the actual data provided below. Be specific with numbers, names, and facts.
Use markdown formatting with headers, bullet points, tables, and bold for key metrics.
Keep responses under 500 words. Highlight critical or urgent items first."""

            user_prompt = f"""User Question: "{query}"

Data Category: {category}
Data Retrieved from Database:
{data_summary}

Based on this data, provide a clear, concise, and helpful response. Be specific with numbers and facts from the data.
Highlight critical or urgent items first. Provide actionable insights when possible.
If the data is empty, say so clearly and suggest what might help.

Response:"""

            loop = asyncio.get_event_loop()

            if _llm_provider == "groq":
                response = await loop.run_in_executor(
                    None,
                    lambda: _llm_client.chat.completions.create(
                        model=_llm_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=1024,
                        temperature=0.7,
                    ),
                )
                text = response.choices[0].message.content
            else:
                response = await loop.run_in_executor(
                    None,
                    lambda: _llm_client.chat_completion(
                        model=_llm_model,
                        messages=[{"role": "user", "content": system_prompt + "\n\n" + user_prompt}],
                        max_tokens=1024,
                        temperature=0.7,
                    ),
                )
                text = response.choices[0].message.content

            if text:
                return text.strip()
            return rule_based_text

        except Exception as e:
            logger.error(f"LLM error (falling back to rule-based): {e}")
            return rule_based_text

    # -- Main query entry point --

    async def ask(
        self,
        query_text: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a natural language query using rule-based routing + optional HuggingFace LLM."""
        start_ms = time.time()

        # Classify and route the query
        route = self._classify_and_route(query_text)
        tool_name = route["tool"]
        params = route["params"]
        category = route["category"]

        tools_called = [{"tool": tool_name, "input": params}]

        # Execute the appropriate query
        try:
            dispatch = {
                "disasters": self._tool_query_disasters,
                "resources": self._tool_query_resources,
                "victim_requests": self._tool_query_victim_requests,
                "predictions": self._tool_query_predictions,
                "resource_utilization": self._tool_query_resource_utilization,
                "anomaly_alerts": self._tool_query_anomaly_alerts,
                "ingested_events": self._tool_query_ingested_events,
                "outcome_tracking": self._tool_query_outcome_tracking,
                "available_resources": self._tool_query_available_resources,
                "users": self._tool_query_users,
            }
            fn = dispatch.get(tool_name)
            if fn:
                data = await fn(params)
                tools_called[0]["result_count"] = len(data) if isinstance(data, list) else 1
            else:
                data = []
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            data = []
            tools_called[0]["error"] = str(e)

        # Format the response (rule-based first)
        rule_based_text = self._format_response(category, data, query_text)

        # Enhance with LLM if available (Groq or HuggingFace)
        if _llm_available:
            response_text = await self._generate_llm_response(query_text, category, data, rule_based_text)
            model_used = _llm_model
        else:
            response_text = rule_based_text
            model_used = "rule-based"

        latency_ms = int((time.time() - start_ms) * 1000)

        # Log to database
        log_record = {
            "user_id": user_id,
            "session_id": session_id,
            "query_text": query_text,
            "query_type": category,
            "tools_called": tools_called,
            "response_text": response_text,
            "response_data": {},
            "model_used": model_used,
            "tokens_used": 0,
            "latency_ms": latency_ms,
        }
        try:
            await db_admin.table("nl_query_log").insert(log_record).async_execute()
        except Exception as e:
            logger.error(f"Failed to log NL query: {e}")

        return {
            "response": response_text,
            "chart_data": None,
            "tools_called": tools_called,
            "tokens_used": 0,
            "latency_ms": latency_ms,
            "model": model_used,
        }

    def _classify_query(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["chart", "graph", "plot", "visualize", "trend"]): return "chart"
        if any(w in q for w in ["recommend", "suggest", "should", "what to do"]): return "recommendation"
        if any(w in q for w in ["compare", "vs", "versus", "difference", "between"]): return "analysis"
        return "data_query"

    # -- Query log retrieval --

    async def get_query_history(self, user_id: Optional[str] = None, session_id: Optional[str] = None, limit: int = 20) -> List[Dict]:
        query = (
            db_admin.table("nl_query_log")
            .select("id, query_text, query_type, response_text, tools_called, latency_ms, feedback_rating, model_used, created_at")
            .order("created_at", desc=True)
            .limit(limit)
        )
        if user_id: query = query.eq("user_id", user_id)
        if session_id: query = query.eq("session_id", session_id)
        resp = await query.async_execute()
        return resp.data or []

    async def submit_feedback(self, query_id: str, rating: int) -> bool:
        try:
            await db_admin.table("nl_query_log").update({"feedback_rating": rating}).eq("id", query_id).async_execute()
            return True
        except Exception as e:
            logger.error(f"Failed to submit feedback: {e}")
            return False
