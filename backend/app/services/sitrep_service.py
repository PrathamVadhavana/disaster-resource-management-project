"""
Phase 5 - Situation Report Generation Service.

Gathers structured data from the database and generates template-based
markdown situation reports - no external AI API needed (free).

New Feature: Structured data snapshot with LLM narration
- Assemble structured data snapshot before generating any sitrep
- Inject snapshot as system prompt context for LLM to narrate
- Output structured 7-section format
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.phase5_config import phase5_config
from app.database import db_admin

logger = logging.getLogger("sitrep_service")


class SitrepService:
    """Generates situation reports with optional LLM enhancement via Groq."""

    def __init__(self):
        self._groq_client = None
        self._groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                from groq import Groq

                self._groq_client = Groq(api_key=groq_key)
                self.model = self._groq_model
                logger.info("SitRep service using Groq LLM: %s", self._groq_model)
            except Exception as e:
                logger.warning("Groq not available for SitRep: %s", e)
                self.model = "rule-based"
        else:
            self.model = "rule-based"

    # -- Data gathering --

    async def _gather_active_disasters(self) -> list[dict]:
        try:
            resp = (
                await db_admin.table("disasters")
                .select(
                    "id, type, severity, status, title, description, affected_population, casualties, estimated_damage, start_date, created_at"
                )
                .in_("status", ["active", "monitoring"])
                .order("created_at", desc=True)
                .limit(50)
                .async_execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"Error fetching disasters: {e}")
            return []

    async def _gather_resource_utilization(self) -> dict:
        try:
            all_resp = (
                await db_admin.table("resources").select("id, type, status, quantity").limit(5000).async_execute()
            )
            resources = all_resp.data or []
            total = len(resources)
            by_status = {}
            by_type = {}
            for r in resources:
                status = r.get("status", "unknown")
                rtype = r.get("type", "other")
                by_status[status] = by_status.get(status, 0) + 1
                by_type[rtype] = by_type.get(rtype, 0) + r.get("quantity", 0)
            # Utilization includes anyone not 'available' or 'idle'
            # Including assigned, occupied, deployed, allocated, etc.
            # Aligning with actual ResourceStatus enum values
            allocated = (
                by_status.get("allocated", 0)
                + by_status.get("deployed", 0)
                + by_status.get("in_transit", 0)
            )
            utilization_pct = round(allocated / total * 100, 1) if total > 0 else 0
            return {
                "total_resources": total,
                "utilization_pct": utilization_pct,
                "by_status": by_status,
                "by_type": by_type,
            }
        except Exception as e:
            logger.error(f"Error fetching resources: {e}")
            return {"total_resources": 0, "utilization_pct": 0, "by_status": {}, "by_type": {}}

    async def _gather_open_requests(self) -> dict:
        try:
            resp = (
                await db_admin.table("resource_requests")
                .select("id, resource_type, priority, status")
                .in_("status", ["pending", "approved", "assigned", "in_progress"])
                .limit(5000)
                .async_execute()
            )
            requests = resp.data or []
            by_priority = {}
            by_type = {}
            by_status = {}
            for r in requests:
                p = r.get("priority", "medium")
                t = r.get("resource_type", "other")
                s = r.get("status", "pending")
                by_priority[p] = by_priority.get(p, 0) + 1
                by_type[t] = by_type.get(t, 0) + 1
                by_status[s] = by_status.get(s, 0) + 1
            return {"total_open": len(requests), "by_priority": by_priority, "by_type": by_type, "by_status": by_status}
        except Exception as e:
            logger.error(f"Error fetching requests: {e}")
            return {"total_open": 0, "by_priority": {}, "by_type": {}, "by_status": {}}

    async def _gather_prediction_summaries(self) -> dict:
        try:
            since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            resp = (
                await db_admin.table("predictions")
                .select("id, prediction_type, confidence_score, predicted_severity, created_at")
                .gte("created_at", since)
                .order("created_at", desc=True)
                .limit(100)
                .async_execute()
            )
            predictions = resp.data or []
            by_type = {}
            avg_confidence = {}
            for p in predictions:
                ptype = p.get("prediction_type", "unknown")
                conf = p.get("confidence_score", 0)
                if ptype not in by_type:
                    by_type[ptype] = 0
                    avg_confidence[ptype] = []
                by_type[ptype] += 1
                avg_confidence[ptype].append(conf)
            for k, v in avg_confidence.items():
                avg_confidence[k] = round(sum(v) / len(v), 3) if v else 0
            return {"total_24h": len(predictions), "by_type": by_type, "avg_confidence": avg_confidence}
        except Exception as e:
            logger.error(f"Error fetching predictions: {e}")
            return {"total_24h": 0, "by_type": {}, "avg_confidence": {}}

    async def _gather_recent_ingestion(self) -> dict:
        try:
            from app.services.ingestion import memory_store

            since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            events = memory_store.query_ingested_events(since=since, limit=500)
            by_type = {}
            by_severity = {}
            processed_count = 0
            for e in events:
                etype = e.get("event_type", "unknown")
                sev = e.get("severity", "unknown")
                by_type[etype] = by_type.get(etype, 0) + 1
                by_severity[sev] = by_severity.get(sev, 0) + 1
                if e.get("processed"):
                    processed_count += 1
            return {
                "total_24h": len(events),
                "processed": processed_count,
                "by_type": by_type,
                "by_severity": by_severity,
            }
        except Exception as e:
            logger.error(f"Error fetching ingestion stats: {e}")
            return {"total_24h": 0, "processed": 0, "by_type": {}, "by_severity": {}}

    async def _gather_anomaly_summary(self) -> dict:
        try:
            resp = (
                await db_admin.table("anomaly_alerts")
                .select("id, anomaly_type, severity, title, status")
                .eq("status", "active")
                .order("detected_at", desc=True)
                .limit(20)
                .async_execute()
            )
            alerts = resp.data or []
            return {
                "active_count": len(alerts),
                "alerts": [{"type": a["anomaly_type"], "severity": a["severity"], "title": a["title"]} for a in alerts],
            }
        except Exception as e:
            logger.error(f"Error fetching anomalies: {e}")
            return {"active_count": 0, "alerts": []}

    async def gather_all_data(self) -> dict[str, Any]:
        results = await asyncio.gather(
            self._gather_active_disasters(),
            self._gather_resource_utilization(),
            self._gather_open_requests(),
            self._gather_prediction_summaries(),
            self._gather_recent_ingestion(),
            self._gather_anomaly_summary(),
            return_exceptions=True,
        )
        return {
            "report_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "active_disasters": results[0] if not isinstance(results[0], Exception) else [],
            "resource_utilization": results[1] if not isinstance(results[1], Exception) else {},
            "open_requests": results[2] if not isinstance(results[2], Exception) else {},
            "prediction_summaries": results[3] if not isinstance(results[3], Exception) else {},
            "ingestion_stats": results[4] if not isinstance(results[4], Exception) else {},
            "anomaly_summary": results[5] if not isinstance(results[5], Exception) else {},
        }

    # ============================================================================
    # NEW: Structured Data Snapshot (per user requirements)
    # ============================================================================

    async def assemble_data_snapshot(self) -> dict[str, Any]:
        """
        Assemble structured data snapshot before generating any sitrep.
        
        Returns data_snapshot with:
        - generated_at
        - active_disasters (with location join, last 10 by severity)
        - request_summary (last 24h, by type, by status, critical_unfulfilled)
        - resource_inventory (by type with available/allocated)
        - top_affected_areas (grouped by location, last 24h)
        - anomalies_active
        - volunteer_activity (verifications_today, accuracy_rate)
        - predictions_summary (high confidence alerts)
        """
        now = datetime.utcnow()
        
        # Gather all data concurrently
        results = await asyncio.gather(
            self._gather_active_disasters_snapshot(),
            self._gather_request_summary_24h(),
            self._gather_resource_inventory(),
            self._gather_top_affected_areas(),
            self._gather_anomalies_active(),
            self._gather_volunteer_activity(),
            self._gather_predictions_summary(),
            return_exceptions=True,
        )
        
        # Build the structured snapshot
        data_snapshot = {
            "generated_at": now.isoformat(),
            "active_disasters": results[0] if not isinstance(results[0], Exception) else [],
            "request_summary": results[1] if not isinstance(results[1], Exception) else {},
            "resource_inventory": results[2] if not isinstance(results[2], Exception) else {},
            "top_affected_areas": results[3] if not isinstance(results[3], Exception) else [],
            "anomalies_active": results[4] if not isinstance(results[4], Exception) else 0,
            "volunteer_activity": results[5] if not isinstance(results[5], Exception) else {},
            "predictions_summary": results[6] if not isinstance(results[6], Exception) else {},
        }
        
        return data_snapshot

    async def _gather_active_disasters_snapshot(self) -> list[dict]:
        """
        Get active disasters with location info, ordered by severity DESC, limit 10.
        Selects: title, type, severity, status, affected_population, location_name, hours_active
        """
        try:
            # Query disasters with status = 'active' ORDER BY severity DESC LIMIT 10
            resp = (
                await db_admin.table("disasters")
                .select("""
                    id, title, type, severity, status, affected_population, 
                    start_date, location_id, created_at
                """)
                .eq("status", "active")
                .order("severity", desc=True)
                .limit(10)
                .async_execute()
            )
            disasters = resp.data or []
            
            # Get location names and calculate hours_active
            enriched_disasters = []
            now = datetime.utcnow()
            
            for d in disasters:
                location_name = "Unknown"
                # Try to get location name from location_id
                if d.get("location_id"):
                    try:
                        loc_resp = await db_admin.table("locations").select("name").eq("id", d["location_id"]).single().execute()
                        if loc_resp.data:
                            location_name = loc_resp.data.get("name", "Unknown")
                    except Exception:
                        pass
                
                # Calculate hours active
                hours_active = 0
                start_date = d.get("start_date") or d.get("created_at")
                if start_date:
                    if isinstance(start_date, str):
                        try:
                            start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                        except Exception:
                            start_date = now
                    hours_active = int((now - start_date).total_seconds() / 3600)
                
                enriched_disasters.append({
                    "title": d.get("title", "Untitled"),
                    "type": d.get("type", "unknown"),
                    "severity": d.get("severity", "unknown"),
                    "status": d.get("status", "unknown"),
                    "affected_population": d.get("affected_population", 0),
                    "location_name": location_name,
                    "hours_active": hours_active,
                })
            
            return enriched_disasters
        except Exception as e:
            logger.error(f"Error in _gather_active_disasters_snapshot: {e}")
            return []

    async def _gather_request_summary_24h(self) -> dict[str, Any]:
        """
        Get resource requests from last 24h:
        - total_last_24h
        - by_type (food, water, etc.)
        - by_status (pending, fulfilled, etc.)
        - critical_unfulfilled (priority >= 8 AND status = 'pending')
        """
        try:
            since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            
            resp = (
                await db_admin.table("resource_requests")
                .select("id, resource_type, priority, status, created_at")
                .gte("created_at", since)
                .async_execute()
            )
            requests = resp.data or []
            
            # Count by type
            by_type = {}
            for r in requests:
                rtype = r.get("resource_type", "other") or "other"
                by_type[rtype] = by_type.get(rtype, 0) + 1
            
            # Count by status
            by_status = {}
            for r in requests:
                status = r.get("status", "pending") or "pending"
                by_status[status] = by_status.get(status, 0) + 1
            
            # Critical unfulfilled (priority >= 8 AND status = 'pending')
            # Note: priority might be string or int
            critical_unfulfilled = 0
            for r in requests:
                priority = r.get("priority", 5)
                # Handle string priorities like "critical", "high", etc.
                if isinstance(priority, str):
                    if priority.lower() in ["critical", "high"]:
                        priority_score = 8
                    elif priority.lower() == "medium":
                        priority_score = 5
                    else:
                        priority_score = 3
                else:
                    priority_score = int(priority) if priority else 5
                
                status = r.get("status", "")
                if priority_score >= 8 and status == "pending":
                    critical_unfulfilled += 1
            
            return {
                "total_last_24h": len(requests),
                "by_type": by_type,
                "by_status": by_status,
                "critical_unfulfilled": critical_unfulfilled,
            }
        except Exception as e:
            logger.error(f"Error in _gather_request_summary_24h: {e}")
            return {"total_last_24h": 0, "by_type": {}, "by_status": {}, "critical_unfulfilled": 0}

    async def _gather_resource_inventory(self) -> dict[str, Any]:
        """
        Get resource inventory by type with available/allocated counts.
        From available_resources table.
        """
        try:
            resp = (
                await db_admin.table("available_resources")
                .select("id, resource_type, quantity, status")
                .async_execute()
            )
            resources = resp.data or []
            
            inventory = {}
            for r in resources:
                rtype = r.get("resource_type", "other") or "other"
                qty = r.get("quantity", 0) or 0
                status = r.get("status", "available") or "available"
                
                if rtype not in inventory:
                    inventory[rtype] = {"available": 0, "allocated": 0}
                
                if status in ["available", "in_stock"]:
                    inventory[rtype]["available"] += qty
                else:
                    inventory[rtype]["allocated"] += qty
            
            return {"by_type": inventory}
        except Exception as e:
            logger.error(f"Error in _gather_resource_inventory: {e}")
            return {"by_type": {}}

    async def _gather_top_affected_areas(self) -> list[dict]:
        """
        Get top affected areas by request count, last 24h.
        Returns: area_name, request_count, latitude, longitude
        """
        try:
            since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            
            # Group by location (using location_id or lat/lng)
            resp = (
                await db_admin.table("resource_requests")
                .select("id, latitude, longitude, location_id")
                .gte("created_at", since)
                .is_("latitude", "not.is.null")
                .async_execute()
            )
            requests = resp.data or []
            
            # Group by rounded lat/lng to create areas
            area_counts = {}
            for r in requests:
                lat = r.get("latitude")
                lng = r.get("longitude")
                loc_id = r.get("location_id")
                
                if lat and lng:
                    # Round to 1 decimal for grouping (~11km grid)
                    area_key = (round(lat, 1), round(lng, 1))
                    if area_key not in area_counts:
                        area_counts[area_key] = {
                            "area_name": f"Area ({area_key[0]}, {area_key[1]})",
                            "request_count": 0,
                            "latitude": area_key[0],
                            "longitude": area_key[1],
                        }
                    area_counts[area_key]["request_count"] += 1
            
            # Sort by count and get top 10
            sorted_areas = sorted(area_counts.values(), key=lambda x: x["request_count"], reverse=True)[:10]
            
            # Try to get location names
            for area in sorted_areas:
                try:
                    # Find closest location
                    loc_resp = await db_admin.table("locations").select("name, latitude, longitude").limit(1).execute()
                    if loc_resp.data and loc_resp.data[0].get("name"):
                        area["area_name"] = loc_resp.data[0]["name"]
                except Exception:
                    pass
            
            return sorted_areas
        except Exception as e:
            logger.error(f"Error in _gather_top_affected_areas: {e}")
            return []

    async def _gather_anomalies_active(self) -> int:
        """Get count of active anomaly alerts."""
        try:
            resp = (
                await db_admin.table("anomaly_alerts")
                .select("id", count="exact")
                .eq("status", "active")
                .async_execute()
            )
            return resp.count or 0
        except Exception as e:
            logger.error(f"Error in _gather_anomalies_active: {e}")
            return 0

    async def _gather_volunteer_activity(self) -> dict[str, Any]:
        """
        Get volunteer activity metrics:
        - verifications_today
        - accuracy_rate (trusted / total * 100)
        """
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Get today's verifications
            verif_resp = (
                await db_admin.table("request_verifications")
                .select("id, verification_status, created_at")
                .gte("created_at", today_start.isoformat())
                .async_execute()
            )
            verifs_today = verif_resp.data or []
            
            # Get total verifications for accuracy calculation
            all_verif_resp = (
                await db_admin.table("request_verifications")
                .select("verification_status")
                .limit(10000)
                .async_execute()
            )
            all_verifs = all_verif_resp.data or []
            
            trusted = len([v for v in all_verifs if v.get("verification_status") == "trusted"])
            total = len(all_verifs)
            accuracy_rate = round((trusted / total * 100) if total > 0 else 0, 1)
            
            return {
                "verifications_today": len(verifs_today),
                "accuracy_rate": f"{accuracy_rate}%",
            }
        except Exception as e:
            logger.error(f"Error in _gather_volunteer_activity: {e}")
            return {"verifications_today": 0, "accuracy_rate": "0%"}

    async def _gather_predictions_summary(self) -> dict[str, Any]:
        """
        Get predictions with confidence > 0.8 and severity in ('high', 'critical').
        Returns list of high_confidence_alerts.
        """
        try:
            resp = (
                await db_admin.table("predictions")
                .select("id, prediction_type, confidence_score, predicted_severity, created_at")
                .gte("confidence_score", 0.8)
                .in_("predicted_severity", ["high", "critical"])
                .order("confidence_score", desc=True)
                .limit(20)
                .async_execute()
            )
            predictions = resp.data or []
            
            high_confidence_alerts = []
            for p in predictions:
                high_confidence_alerts.append({
                    "id": p.get("id", ""),
                    "prediction_type": p.get("prediction_type", "unknown"),
                    "confidence": p.get("confidence_score", 0),
                    "severity": p.get("predicted_severity", "unknown"),
                })
            
            return {"high_confidence_alerts": high_confidence_alerts}
        except Exception as e:
            logger.error(f"Error in _gather_predictions_summary: {e}")
            return {"high_confidence_alerts": []}

    # ============================================================================
    # NEW: LLM-based SitRep Generation with System Prompt Injection
    # ============================================================================

    async def generate_sitrep_with_llm(self, data_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Generate a structured sitrep using LLM narration.
        
        1. If data_snapshot not provided, assemble it first
        2. Inject snapshot as system prompt context
        3. Use LLM to narrate the data
        4. Return structured 7-section output
        
        Output structure:
        1. Executive Summary (2-3 sentences)
        2. Active Disasters (table or list)
        3. Resource Needs Analysis
        4. Geographic Hotspots
        5. Operational Metrics
        6. Recommended Actions (3-5 bullets)
        7. Anomalies & Alerts
        """
        # Assemble snapshot if not provided
        if data_snapshot is None:
            data_snapshot = await self.assemble_data_snapshot()
        
        # Generate sitrep using LLM if available, otherwise use template
        if self._groq_client:
            return await self._generate_llm_sitrep(data_snapshot)
        else:
            return await self._generate_template_sitrep(data_snapshot)

    async def _generate_llm_sitrep(self, data_snapshot: dict[str, Any]) -> dict[str, Any]:
        """Generate sitrep using Groq LLM with system prompt injection."""
        try:
            # Build system prompt with data snapshot
            system_prompt = self._build_sitrep_system_prompt(data_snapshot)
            
            user_prompt = """Based on the data snapshot provided, generate a structured situation report (sitrep) with the following sections:

1. Executive Summary (2-3 sentences)
2. Active Disasters (table or list)
3. Resource Needs Analysis
4. Geographic Hotspots
5. Operational Metrics
6. Recommended Actions (3-5 bullets, DERIVED from data - e.g., 'Food requests in [area] are 3x the 7-day average - consider pre-positioning stock')
7. Anomalies & Alerts

IMPORTANT: Only use data from the snapshot. Do NOT invent information. Derive recommendations from the actual data provided.

Format your response using markdown with clear section headers."""
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._groq_client.chat.completions.create(
                    model=self._groq_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=2048,
                    temperature=0.3,
                ),
            )
            
            sitrep_text = response.choices[0].message.content or ""
            
            # Parse the response and structure it
            return {
                "generated_at": data_snapshot.get("generated_at"),
                "sitrep_text": sitrep_text,
                "data_snapshot": data_snapshot,
                "model_used": self.model,
                "sections": self._parse_sitrep_sections(sitrep_text),
            }
        except Exception as e:
            logger.error(f"Error generating LLM sitrep: {e}")
            # Fall back to template
            return await self._generate_template_sitrep(data_snapshot)

    def _build_sitrep_system_prompt(self, data_snapshot: dict[str, Any]) -> str:
        """Build system prompt with data snapshot as context."""
        
        # Format the data as JSON for the prompt
        snapshot_json = json.dumps(data_snapshot, indent=2, default=str)
        
        system_prompt = f"""You are the AI coordinator for a disaster management platform called HopeInChaos.
Your role is to analyze disaster data and generate accurate situation reports (sit-reps).

CRITICAL RULES:
1. ONLY use data from the provided snapshot - do NOT invent information
2. Derive recommendations from actual data patterns (e.g., 'Food requests in [area] are 3x the 7-day average')
3. Be factual and specific - cite actual numbers from the data
4. If data is missing or zero, state that explicitly

DATA SNAPSHOT:
{snapshot_json}

When generating recommendations, look for patterns like:
- High request counts in specific areas
- Critical unfulfilled requests (priority >= 8)
- Low resource inventory vs high demand
- Active anomalies requiring attention
- High-confidence ML predictions

Provide accurate, data-driven sitreps."""
        
        return system_prompt

    def _parse_sitrep_sections(self, sitrep_text: str) -> dict[str, str]:
        """Parse sitrep text into structured sections."""
        sections = {
            "executive_summary": "",
            "active_disasters": "",
            "resource_needs": "",
            "geographic_hotspots": "",
            "operational_metrics": "",
            "recommended_actions": "",
            "anomalies_alerts": "",
        }
        
        current_section = None
        lines = sitrep_text.split("\n")
        
        for line in lines:
            lower = line.lower().strip()
            
            if "executive summary" in lower:
                current_section = "executive_summary"
                continue
            elif "active disaster" in lower:
                current_section = "active_disasters"
                continue
            elif "resource need" in lower:
                current_section = "resource_needs"
                continue
            elif "geographic hotspot" in lower or "hotspot" in lower:
                current_section = "geographic_hotspots"
                continue
            elif "operational metric" in lower:
                current_section = "operational_metrics"
                continue
            elif "recommended action" in lower or "recommendation" in lower:
                current_section = "recommended_actions"
                continue
            elif "anomal" in lower or "alert" in lower:
                current_section = "anomalies_alerts"
                continue
            
            if current_section:
                sections[current_section] += line + "\n"
        
        return sections

    async def _generate_template_sitrep(self, data_snapshot: dict[str, Any]) -> dict[str, Any]:
        """Generate sitrep using template-based approach (fallback)."""
        
        # Build sitrep from data snapshot
        lines = []
        
        # Header
        lines.append(f"# Situation Report - Generated {data_snapshot.get('generated_at', 'N/A')}\n")
        
        # 1. Executive Summary
        lines.append("## 1. Executive Summary\n")
        active_disasters = data_snapshot.get("active_disasters", [])
        request_summary = data_snapshot.get("request_summary", {})
        total_requests = request_summary.get("total_last_24h", 0)
        critical_unfulfilled = request_summary.get("critical_unfulfilled", 0)
        
        if len(active_disasters) == 0:
            lines.append("No active disasters at this time. System is in standby mode.\n")
        else:
            critical_count = len([d for d in active_disasters if d.get("severity") == "critical"])
            lines.append(
                f"Currently tracking **{len(active_disasters)} active disaster(s)**"
                f" ({critical_count} critical). "
                f"Resource requests in the last 24h: **{total_requests}** "
                f"({critical_unfulfilled} critical unfulfilled)."
            )
            lines.append("")
        
        # 2. Active Disasters
        lines.append("## 2. Active Disasters\n")
        if active_disasters:
            lines.append("| Title | Type | Severity | Status | Affected | Location | Hours Active |")
            lines.append("|-------|------|----------|--------|----------|----------|---------------|")
            for d in active_disasters:
                lines.append(
                    f"| {d.get('title', 'N/A')} | {d.get('type', 'N/A')} | "
                    f"{d.get('severity', 'N/A')} | {d.get('status', 'N/A')} | "
                    f"{d.get('affected_population', 0):,} | {d.get('location_name', 'N/A')} | "
                    f"{d.get('hours_active', 0)} |"
                )
            lines.append("")
        else:
            lines.append("No active disasters.\n")
        
        # 3. Resource Needs Analysis
        lines.append("## 3. Resource Needs Analysis\n")
        lines.append(f"**Requests (last 24h):** {total_requests}\n")
        
        by_type = request_summary.get("by_type", {})
        if by_type:
            lines.append("\n**By Type:**")
            for rtype, count in sorted(by_type.items(), key=lambda x: -x[1]):
                lines.append(f"- {rtype}: {count}")
        
        by_status = request_summary.get("by_status", {})
        if by_status:
            lines.append("\n**By Status:**")
            for status, count in sorted(by_status.items()):
                lines.append(f"- {status}: {count}")
        
        if critical_unfulfilled > 0:
            lines.append(f"\n> **WARNING:** {critical_unfulfilled} critical request(s) (priority >= 8) remain unfulfilled!\n")
        lines.append("")
        
        # 4. Geographic Hotspots
        lines.append("## 4. Geographic Hotspots\n")
        top_areas = data_snapshot.get("top_affected_areas", [])
        if top_areas:
            lines.append("| Area | Request Count | Coordinates |")
            lines.append("|------|---------------|-------------|")
            for area in top_areas:
                lines.append(
                    f"| {area.get('area_name', 'Unknown')} | {area.get('request_count', 0)} | "
                    f"({area.get('latitude', 0)}, {area.get('longitude', 0)}) |"
                )
            lines.append("")
        else:
            lines.append("No geographic hotspots identified.\n")
        
        # 5. Operational Metrics
        lines.append("## 5. Operational Metrics\n")
        
        # Resource inventory
        resource_inv = data_snapshot.get("resource_inventory", {})
        inv_by_type = resource_inv.get("by_type", {})
        if inv_by_type:
            lines.append("**Resource Inventory:**")
            lines.append("| Type | Available | Allocated |")
            lines.append("|------|-----------|------------|")
            for rtype, counts in sorted(inv_by_type.items()):
                lines.append(f"| {rtype} | {counts.get('available', 0)} | {counts.get('allocated', 0)} |")
            lines.append("")
        
        # Volunteer activity
        vol_activity = data_snapshot.get("volunteer_activity", {})
        lines.append(f"**Volunteer Activity:**")
        lines.append(f"- Verifications today: {vol_activity.get('verifications_today', 0)}")
        lines.append(f"- Accuracy rate: {vol_activity.get('accuracy_rate', '0%')}\n")
        
        # Predictions
        preds = data_snapshot.get("predictions_summary", {})
        high_conf_preds = preds.get("high_confidence_alerts", [])
        lines.append(f"**ML Predictions:** {len(high_conf_preds)} high-confidence alerts")
        if high_conf_preds:
            for p in high_conf_preds[:5]:
                lines.append(f"- {p.get('prediction_type')}: {p.get('confidence')*100:.0f}% confidence, {p.get('severity')} severity")
        lines.append("")
        
        # 6. Recommended Actions
        lines.append("## 6. Recommended Actions\n")
        recommendations = []
        
        if critical_unfulfilled > 0:
            recommendations.append(f"**Urgent:** Address {critical_unfulfilled} critical unfulfilled requests immediately")
        
        if len(active_disasters) > 5:
            recommendations.append(f"Consider additional resource pre-positioning for {len(active_disasters)} active disasters")
        
        if top_areas and top_areas[0].get("request_count", 0) > 20:
            top_area = top_areas[0]
            recommendations.append(f"High request volume in {top_area.get('area_name')} ({top_area.get('request_count')} requests) - verify inventory levels")
        
        anomalies_active = data_snapshot.get("anomalies_active", 0)
        if anomalies_active > 0:
            recommendations.append(f"Review {anomalies_active} active anomaly alert(s) for potential operational issues")
        
        # Check for resource shortages
        if inv_by_type:
            for rtype, counts in inv_by_type.items():
                if counts.get("available", 0) < counts.get("allocated", 0) * 0.5:
                    recommendations.append(f"Low {rtype} availability ({counts.get('available', 0)} available vs {counts.get('allocated', 0)} allocated) - consider emergency procurement")
        
        if not recommendations:
            recommendations.append("Continue standard monitoring operations")
        
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")
        
        # 7. Anomalies & Alerts
        lines.append("## 7. Anomalies & Alerts\n")
        if anomalies_active > 0:
            lines.append(f"**{anomalies_active} active anomaly alert(s) require attention.**")
            lines.append("Review anomaly dashboard for details.")
        else:
            lines.append("No active anomaly alerts.")
        
        sitrep_text = "\n".join(lines)
        
        return {
            "generated_at": data_snapshot.get("generated_at"),
            "sitrep_text": sitrep_text,
            "data_snapshot": data_snapshot,
            "model_used": "template",
            "sections": self._parse_sitrep_sections(sitrep_text),
        }

    # -- Template-based report generation (free) --

    def _generate_markdown(self, data: dict[str, Any], report_type: str) -> str:
        disasters = data.get("active_disasters", [])
        resources = data.get("resource_utilization", {})
        requests = data.get("open_requests", {})
        predictions = data.get("prediction_summaries", {})
        ingestion = data.get("ingestion_stats", {})
        anomalies = data.get("anomaly_summary", {})

        lines = []
        # Header removed as per UI redundancy fix
        lines.append(f"*{report_type.title()} report generated at {data['generated_at']} UTC*\n")

        # Executive Summary
        lines.append("## 1. Executive Summary\n")
        n_disasters = len(disasters)
        critical_disasters = [d for d in disasters if d.get("severity") == "critical"]
        util_pct = resources.get("utilization_pct", 0)
        total_requests = requests.get("total_open", 0)
        critical_requests = requests.get("by_priority", {}).get("critical", 0)
        n_anomalies = anomalies.get("active_count", 0)

        if n_disasters == 0:
            lines.append("No active disasters at this time. System is in standby mode.\n")
        else:
            parts = [f"Currently tracking **{n_disasters} active disaster(s)**"]
            if critical_disasters:
                parts.append(f" with **{len(critical_disasters)} at critical severity**")
            parts.append(
                f". Resource utilization is at **{util_pct}%** with **{total_requests} open victim request(s)**"
            )
            if critical_requests:
                parts.append(f" ({critical_requests} critical)")
            parts.append(".")
            if n_anomalies:
                parts.append(f" **{n_anomalies} anomaly alert(s) require attention.**")
            lines.append("".join(parts) + "\n")

        # Key Metrics
        lines.append("## 2. Key Metrics Dashboard\n")
        lines.append(f"- **Active Disasters:** {n_disasters}")
        lines.append(f"- **Resource Utilization:** {util_pct}%")
        lines.append(f"- **Total Resources:** {resources.get('total_resources', 0)}")
        lines.append(f"- **Open Victim Requests:** {total_requests}")
        lines.append(f"  - Critical: {critical_requests}")
        lines.append(f"  - High: {requests.get('by_priority', {}).get('high', 0)}")
        lines.append(f"- **ML Predictions (24h):** {predictions.get('total_24h', 0)}")
        lines.append(
            f"- **Ingested Events (24h):** {ingestion.get('total_24h', 0)} ({ingestion.get('processed', 0)} processed)"
        )
        lines.append(f"- **Active Anomaly Alerts:** {n_anomalies}\n")

        # Active Disasters
        lines.append("## 3. Active Disasters Status\n")
        if disasters:
            for d in disasters[:10]:
                sev = d.get("severity", "unknown").upper()
                lines.append(f"### {d.get('title', 'Untitled')} [{sev}]")
                lines.append(f"- **Type:** {d.get('type', 'unknown')}")
                lines.append(f"- **Status:** {d.get('status', 'unknown')}")
                if d.get("affected_population"):
                    lines.append(f"- **Affected Population:** {d['affected_population']:,}")
                if d.get("casualties"):
                    lines.append(f"- **Casualties:** {d['casualties']:,}")
                if d.get("estimated_damage"):
                    lines.append(f"- **Estimated Damage:** ${d['estimated_damage']:,.0f}")
                if d.get("description"):
                    lines.append(f"- {d['description'][:200]}")
                lines.append("")
        else:
            lines.append("No active disasters.\n")

        # Resource Status
        lines.append("## 4. Resource Status & Gaps\n")
        by_status = resources.get("by_status", {})
        if by_status:
            lines.append("| Status | Count |")
            lines.append("|--------|-------|")
            for status, count in sorted(by_status.items()):
                lines.append(f"| {status} | {count} |")
            lines.append("")
        by_type = resources.get("by_type", {})
        if by_type:
            lines.append("**Quantity by type:**")
            for rtype, qty in sorted(by_type.items()):
                lines.append(f"- {rtype}: {qty:,}")
            lines.append("")
        if util_pct > 80:
            lines.append("> Warning: **Resource utilization above 80%** - consider mobilizing additional supplies.\n")

        # Victim Requests
        lines.append("## 5. Victim Requests Analysis\n")
        lines.append(f"**{total_requests}** open requests.\n")
        by_req_status = requests.get("by_status", {})
        if by_req_status:
            lines.append("| Status | Count |")
            lines.append("|--------|-------|")
            for s, c in sorted(by_req_status.items()):
                lines.append(f"| {s} | {c} |")
            lines.append("")
        by_req_type = requests.get("by_type", {})
        if by_req_type:
            lines.append("**By resource type:**")
            for t, c in sorted(by_req_type.items(), key=lambda x: -x[1]):
                lines.append(f"- {t}: {c}")
            lines.append("")
        if critical_requests:
            lines.append(f"> **{critical_requests} critical request(s)** need immediate attention.\n")

        # ML Predictions
        lines.append("## 6. ML Predictions & Trends\n")
        pred_total = predictions.get("total_24h", 0)
        if pred_total:
            lines.append(f"**{pred_total}** predictions generated in the last 24 hours.\n")
            pred_by_type = predictions.get("by_type", {})
            avg_conf = predictions.get("avg_confidence", {})
            if pred_by_type:
                lines.append("| Type | Count | Avg Confidence |")
                lines.append("|------|-------|----------------|")
                for ptype, count in sorted(pred_by_type.items()):
                    conf = avg_conf.get(ptype, 0)
                    conf_str = f"{conf:.1%}" if isinstance(conf, (int, float)) else str(conf)
                    lines.append(f"| {ptype} | {count} | {conf_str} |")
                lines.append("")
        else:
            lines.append("No predictions generated in the last 24 hours.\n")

        # Anomalies
        lines.append("## 7. Anomalies & Alerts\n")
        if n_anomalies:
            for alert in anomalies.get("alerts", [])[:5]:
                lines.append(
                    f"- **[{alert.get('severity', 'medium').upper()}]** {alert.get('title', 'Unknown')} ({alert.get('type', '')})"
                )
            lines.append("")
        else:
            lines.append("No active anomaly alerts.\n")

        # Recommendations
        lines.append("## 8. Recommendations\n")
        rec_num = 1
        if critical_disasters:
            lines.append(
                f"{rec_num}. **Prioritize critical-severity disasters** - {len(critical_disasters)} disaster(s) at critical level require immediate attention."
            )
            rec_num += 1
        if critical_requests:
            lines.append(
                f"{rec_num}. **Address critical victim requests** - {critical_requests} request(s) marked critical are awaiting action."
            )
            rec_num += 1
        if util_pct > 80:
            lines.append(f"{rec_num}. **Replenish resources** - utilization is at {util_pct}%, risking shortages.")
            rec_num += 1
        if n_anomalies:
            lines.append(
                f"{rec_num}. **Investigate anomaly alerts** - {n_anomalies} active alert(s) may indicate emerging issues."
            )
            rec_num += 1
        pending_count = by_req_status.get("pending", 0) if by_req_status else 0
        if pending_count > 10:
            lines.append(f"{rec_num}. **Clear request backlog** - {pending_count} requests still in pending status.")
            rec_num += 1
        if rec_num == 1:
            lines.append("No urgent recommendations at this time. Continue monitoring.")
        lines.append("")
        lines.append("---")
        lines.append(
            f"*Report generated by {'Groq LLM + ' if self._groq_client else ''}Rule-Based SitRep Engine - {data['generated_at']} UTC*"
        )
        return "\n".join(lines)

    async def _enhance_with_llm(self, markdown: str, data: dict[str, Any]) -> str:
        """Optionally enhance the executive summary and recommendations using Groq."""
        if not self._groq_client:
            return markdown

        try:
            import asyncio

            # Build a concise data summary for the LLM
            disasters = data.get("active_disasters", [])
            resources = data.get("resource_utilization", {})
            requests = data.get("open_requests", {})
            anomalies = data.get("anomaly_summary", {})

            data_summary = json.dumps(
                {
                    "active_disasters": len(disasters),
                    "critical_disasters": [d.get("title", "?") for d in disasters if d.get("severity") == "critical"],
                    "utilization_pct": resources.get("utilization_pct", 0),
                    "total_resources": resources.get("total_resources", 0),
                    "open_requests": requests.get("total_open", 0),
                    "critical_requests": requests.get("by_priority", {}).get("critical", 0),
                    "anomalies": anomalies.get("active_count", 0),
                    "disaster_details": [
                        {
                            "title": d.get("title"),
                            "type": d.get("type"),
                            "severity": d.get("severity"),
                            "affected": d.get("affected_population"),
                            "casualties": d.get("casualties"),
                        }
                        for d in disasters[:10]
                    ],
                },
                default=str,
                indent=2,
            )

            prompt = f"""You are the AI coordinator for HopeInChaos, a disaster management platform.
Given this platform data, write ONLY two sections:

1. A 3-5 sentence executive summary highlighting the most critical situation, key metrics, and overall system health.
2. A numbered list of 3-5 prioritized actionable recommendations.

Platform Data:
{data_summary}

Format your response exactly like this:
EXECUTIVE_SUMMARY:
[Your summary here]

RECOMMENDATIONS:
1. [Recommendation]
2. [Recommendation]
..."""

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._groq_client.chat.completions.create(
                    model=self._groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512,
                    temperature=0.5,
                ),
            )
            llm_text = response.choices[0].message.content or ""

            # Replace the executive summary section
            if "EXECUTIVE_SUMMARY:" in llm_text:
                exec_start = llm_text.index("EXECUTIVE_SUMMARY:") + len("EXECUTIVE_SUMMARY:")
                exec_end = llm_text.index("RECOMMENDATIONS:") if "RECOMMENDATIONS:" in llm_text else len(llm_text)
                new_summary = llm_text[exec_start:exec_end].strip()

                # Replace between "## 1. Executive Summary" and "## 2."
                import re

                markdown = re.sub(
                    r"(## 1\. Executive Summary\n\n)(.*?)(\n## 2\.)",
                    rf"\g<1>{new_summary}\n\n\g<3>",
                    markdown,
                    flags=re.DOTALL,
                )

            # Replace the recommendations section
            if "RECOMMENDATIONS:" in llm_text:
                rec_start = llm_text.index("RECOMMENDATIONS:") + len("RECOMMENDATIONS:")
                new_recs = llm_text[rec_start:].strip()

                import re

                markdown = re.sub(
                    r"(## 8\. Recommendations\n\n)(.*?)(\n---)",
                    rf"\g<1>{new_recs}\n\n\g<3>",
                    markdown,
                    flags=re.DOTALL,
                )

            return markdown
        except Exception as e:
            logger.warning("LLM enhancement failed (using template): %s", e)
            return markdown

    # -- Report generation --

    async def generate_report(self, report_type: str = "daily", generated_by: str = "system") -> dict[str, Any]:
        start_ms = time.time()
        data = await self.gather_all_data()
        try:
            markdown_body = self._generate_markdown(data, report_type)
            # Enhance with LLM if available (Groq)
            markdown_body = await self._enhance_with_llm(markdown_body, data)
            generation_time = int((time.time() - start_ms) * 1000)
            lines = markdown_body.strip().split("\n")
            title = f"Situation Report - {data['report_date']}"
            for line in lines:
                if line.startswith("# "):
                    title = line.lstrip("# ").strip()
                    break
            summary = ""
            in_exec = False
            for line in lines:
                if "Executive Summary" in line:
                    in_exec = True
                    continue
                if in_exec and line.strip() and not line.startswith("#"):
                    summary = line.strip()
                    break
            key_metrics = {
                "active_disasters": len(data.get("active_disasters", [])),
                "resource_utilization_pct": data.get("resource_utilization", {}).get("utilization_pct", 0),
                "total_open_requests": data.get("open_requests", {}).get("total_open", 0),
                "critical_requests": data.get("open_requests", {}).get("by_priority", {}).get("critical", 0),
                "predictions_24h": data.get("prediction_summaries", {}).get("total_24h", 0),
                "active_anomalies": data.get("anomaly_summary", {}).get("active_count", 0),
                "ingested_events_24h": data.get("ingestion_stats", {}).get("total_24h", 0),
            }
            record = {
                "report_date": data["report_date"],
                "report_type": report_type,
                "title": title,
                "markdown_body": markdown_body,
                "summary": summary,
                "key_metrics": key_metrics,
                "recommendations": [],
                "model_used": self.model,
                "generated_by": generated_by,
                "generation_time_ms": generation_time,
                "status": "generated",
            }
            db_resp = await db_admin.table("situation_reports").insert(record).async_execute()
            stored = db_resp.data[0] if db_resp.data else record
            if phase5_config.SITREP_EMAIL_ENABLED and phase5_config.SITREP_ADMIN_EMAILS:
                await self._email_report(stored, phase5_config.SITREP_ADMIN_EMAILS)
            logger.info(f"Situation report generated in {generation_time}ms: {title}")
            return stored
        except Exception as e:
            generation_time = int((time.time() - start_ms) * 1000)
            logger.error(f"Failed to generate situation report: {e}")
            error_record = {
                "report_date": data["report_date"],
                "report_type": report_type,
                "title": f"FAILED: Situation Report - {data['report_date']}",
                "markdown_body": "",
                "model_used": self.model,
                "generated_by": generated_by,
                "generation_time_ms": generation_time,
                "status": "failed",
                "error_message": str(e),
            }
            try:
                await db_admin.table("situation_reports").insert(error_record).async_execute()
            except Exception:
                pass
            raise

    async def _email_report(self, report: dict, recipients: list[str]) -> None:
        if not phase5_config.SENDGRID_API_KEY:
            logger.warning("SendGrid not configured, skipping email")
            return
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for email in recipients:
                    await client.post(
                        "https://api.sendgrid.com/v3/mail/send",
                        headers={
                            "Authorization": f"Bearer {phase5_config.SENDGRID_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "personalizations": [{"to": [{"email": email}]}],
                            "from": {"email": phase5_config.SENDGRID_FROM_EMAIL},
                            "subject": report.get("title", "Situation Report"),
                            "content": [{"type": "text/plain", "value": report.get("markdown_body", "")}],
                        },
                    )
            await (
                db_admin.table("situation_reports")
                .update({"emailed_to": recipients, "status": "emailed"})
                .eq("id", report["id"])
                .async_execute()
            )
        except Exception as e:
            logger.error(f"Failed to email report: {e}")

    # -- List & get reports --

    async def list_reports(self, report_type: str | None = None, limit: int = 20, offset: int = 0) -> list[dict]:
        try:
            query = (
                db_admin.table("situation_reports")
                .select(
                    "id, report_date, report_type, title, summary, key_metrics, status, generation_time_ms, created_at"
                )
                .order("report_date", desc=True)
                .range(offset, offset + limit - 1)
            )
            if report_type:
                query = query.eq("report_type", report_type)
            resp = await query.async_execute()
            return resp.data or []
        except Exception as e:
            logger.warning("Failed to list reports: %s", e)
            return []

    async def get_report(self, report_id: str) -> dict | None:
        try:
            resp = await db_admin.table("situation_reports").select("*").eq("id", report_id).single().async_execute()
            return resp.data
        except Exception as e:
            logger.warning("Failed to get report %s: %s", report_id, e)
            return None

    async def get_latest_report(self) -> dict | None:
        try:
            resp = (
                await db_admin.table("situation_reports")
                .select("*")
                .eq("status", "generated")
                .order("created_at", desc=True)
                .limit(1)
                .async_execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.warning("Failed to get latest report: %s", e)
            return None
