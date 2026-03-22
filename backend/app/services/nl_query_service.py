"""
Phase 5 - Natural Language Query Service.

Provides a 'Chat with your data' interface using BOTH:
1. Rule-based keyword matching for DB queries (fast, free)
2. Groq API for intelligent response generation

Falls back to rule-based formatting if no API key is configured.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any

from app.database import db_admin
from app.services.forecast_service import generate_forecast, ConsumptionRecord, ForecastResult

logger = logging.getLogger("nl_query_service")

# LLM State — Groq API for LLM enhancement
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
        logger.warning("groq package not installed — using rule-based NL query mode")
    except Exception as e:
        logger.warning(f"Groq setup failed: {e} — using rule-based NL query mode")


class NLQueryService:
    """Natural language query interface with optional Groq LLM enhancement."""

    def __init__(self):
        self.model = _llm_model if _llm_available else "rule-based"

    # -- Tool execution (same DB queries as before) --

    async def _tool_query_disasters(self, params: dict) -> Any:
        query = db_admin.table("disasters").select("*")
        if params.get("id"):
            query = query.eq("id", params["id"])

        if params.get("status"):
            query = query.eq("status", params["status"])
        if params.get("severity"):
            query = query.eq("severity", params["severity"])
        if params.get("disaster_type"):
            query = query.eq("type", params["disaster_type"])
        query = query.order("created_at", desc=True).limit(params.get("limit", 20))
        return (await query.async_execute()).data or []

    async def _tool_query_resources(self, params: dict) -> Any:
        query = db_admin.table("resources").select("*")
        if params.get("id"):
            query = query.eq("id", params["id"])
        if params.get("status"):
            query = query.eq("status", params["status"])
        if params.get("resource_type"):
            query = query.eq("type", params["resource_type"])
        if params.get("disaster_id"):
            query = query.eq("disaster_id", params["disaster_id"])
        query = query.limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    async def _tool_query_victim_requests(self, params: dict) -> Any:
        query = db_admin.table("resource_requests").select("*")
        if params.get("status"):
            query = query.eq("status", params["status"])
        if params.get("priority"):
            query = query.eq("priority", params["priority"])
        if params.get("resource_type"):
            query = query.eq("resource_type", params["resource_type"])
        query = query.order("created_at", desc=True).limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    async def _tool_query_predictions(self, params: dict) -> Any:
        query = db_admin.table("predictions").select("*")
        if params.get("prediction_type"):
            query = query.eq("prediction_type", params["prediction_type"])
        if params.get("since_hours"):
            since = (datetime.utcnow() - timedelta(hours=params["since_hours"])).isoformat()
            query = query.gte("created_at", since)
        if params.get("min_confidence"):
            query = query.gte("confidence_score", params["min_confidence"])
        query = query.order("created_at", desc=True).limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    async def _tool_query_resource_utilization(self, params: dict) -> Any:
        resp = await db_admin.table("resources").select("id, type, status, quantity").async_execute()
        resources = resp.data or []
        total = len(resources)
        by_status = {}
        by_type = {}
        total_quantity_by_type = {}
        for r in resources:
            status = r.get("status", "unknown")
            rtype = r.get("type", "other")
            qty = r.get("quantity", 0)
            by_status[status] = by_status.get(status, 0) + 1
            by_type[rtype] = by_type.get(rtype, 0) + 1
            total_quantity_by_type[rtype] = total_quantity_by_type.get(rtype, 0) + qty
        allocated = by_status.get("allocated", 0) + by_status.get("deployed", 0) + by_status.get("in_transit", 0)
        utilization_pct = round(float(allocated) / total * 100, 1) if total > 0 else 0.0
        return {
            "total_resources": total,
            "utilization_pct": utilization_pct,
            "by_status": by_status,
            "by_type": by_type,
            "total_quantity_by_type": total_quantity_by_type,
        }

    async def _tool_query_anomaly_alerts(self, params: dict) -> Any:
        query = db_admin.table("anomaly_alerts").select("*")
        if params.get("status"):
            query = query.eq("status", params["status"])
        if params.get("severity"):
            query = query.eq("severity", params["severity"])
        if params.get("anomaly_type"):
            query = query.eq("anomaly_type", params["anomaly_type"])
        query = query.order("detected_at", desc=True).limit(params.get("limit", 20))
        return (await query.async_execute()).data or []

    async def _tool_query_ingested_events(self, params: dict) -> Any:
        from app.services.ingestion import memory_store

        since = None
        if params.get("since_hours"):
            since = (datetime.utcnow() - timedelta(hours=params["since_hours"])).isoformat()
        return memory_store.query_ingested_events(
            event_type=params.get("event_type"),
            since=since,
            limit=params.get("limit", 50),
        )

    async def _tool_query_outcome_tracking(self, params: dict) -> Any:
        query = db_admin.table("outcome_tracking").select("*")
        if params.get("prediction_type"):
            query = query.eq("prediction_type", params["prediction_type"])
        query = query.order("created_at", desc=True).limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    async def _tool_query_available_resources(self, params: dict) -> Any:
        query = db_admin.table("resources").select("*").eq("status", "available")
        if params.get("category"):
            query = query.eq("type", params["category"].lower())
        query = query.order("type").limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    async def _tool_query_users(self, params: dict) -> Any:
        query = db_admin.table("users").select("id, full_name, email, role, created_at")
        if params.get("role"):
            query = query.eq("role", params["role"])
        query = query.order("created_at", desc=True).limit(params.get("limit", 50))
        return (await query.async_execute()).data or []

    # -- New query handlers for enhanced intents --

    async def _tool_query_resource_requests_by_type_and_time(self, params: dict) -> dict[str, Any]:
        """
        Intent: "how many [resource_type] requests in the last [N] days"
        Query: SELECT count(*), resource_type FROM resource_requests 
               WHERE created_at > now()-interval AND resource_type = X GROUP BY resource_type
        """
        resource_type = params.get("resource_type", "")
        days = params.get("days", 7)
        
        # Build raw SQL for transparency
        raw_sql = f"""SELECT count(*) as count, resource_type 
FROM resource_requests 
WHERE created_at > now() - interval '{days} days' 
{'AND resource_type = \'' + resource_type + '\'' if resource_type else ''} 
GROUP BY resource_type"""
        
        # Execute raw SQL
        query = """
            SELECT count(*) as count, resource_type 
            FROM resource_requests 
            WHERE created_at > now() - interval '1 day' * :days
        """
        
        if resource_type:
            query += " AND resource_type = :resource_type"
        
        query += " GROUP BY resource_type"
        
        try:
            # Use parameterized query
            exec_params = {"days": days}
            if resource_type:
                exec_params["resource_type"] = resource_type
            
            # Supabase raw query
            resp = await db_admin.rpc("exec_sql", {
                "query": query,
                "params": json.dumps(exec_params)
            }).execute() if hasattr(db_admin, 'rpc') else None
            
            if not resp or not resp.data:
                # Fallback: use table query
                table_query = db_admin.table("resource_requests").select("resource_type")
                since = (datetime.utcnow() - timedelta(days=days)).isoformat()
                table_query = table_query.gte("created_at", since)
                if resource_type:
                    table_query = table_query.eq("resource_type", resource_type)
                resp = await table_query.execute()
                
                # Count by resource_type
                counts = {}
                for row in resp.data or []:
                    rt = row.get("resource_type", "unknown")
                    counts[rt] = counts.get(rt, 0) + 1
                
                result = [{"count": v, "resource_type": k} for k, v in counts.items()]
            else:
                result = resp.data
                raw_sql = query
        except Exception as e:
            logger.error(f"Error in resource_requests_by_type_and_time: {e}")
            # Fallback query
            table_query = db_admin.table("resource_requests").select("resource_type")
            since = (datetime.utcnow() - timedelta(days=days)).isoformat()
            table_query = table_query.gte("created_at", since)
            if resource_type:
                table_query = table_query.eq("resource_type", resource_type)
            resp = await table_query.execute()
            
            counts = {}
            for row in resp.data or []:
                rt = row.get("resource_type", "unknown")
                counts[rt] = counts.get(rt, 0) + 1
            
            result = [{"count": v, "resource_type": k} for k, v in counts.items()]
            raw_sql = f"SELECT count(*) as count, resource_type FROM resource_requests WHERE created_at > now() - interval '{days} days' GROUP BY resource_type"
        
        return {
            "data": result,
            "raw_sql": raw_sql,
            "days": days,
            "resource_type": resource_type
        }

    async def _tool_query_area_with_most_requests(self, params: dict) -> dict[str, Any]:
        """
        Intent: "which area has the most requests"
        Query: SELECT latitude, longitude, count(*) FROM resource_requests 
               WHERE latitude IS NOT NULL 
               GROUP BY round(latitude,1), round(longitude,1) 
               ORDER BY count DESC LIMIT 5
        Then reverse geocode using nearest location from locations table
        """
        limit = params.get("limit", 5)
        
        raw_sql = f"""SELECT round(latitude, 1) as lat, round(longitude, 1) as lng, count(*) as request_count
FROM resource_requests
WHERE latitude IS NOT NULL AND longitude IS NOT NULL
GROUP BY round(latitude, 1), round(longitude, 1)
ORDER BY request_count DESC
LIMIT {limit}"""
        
        try:
            # Get aggregated request counts by area
            query = db_admin.table("resource_requests").select("latitude, longitude")
            query = query.is_("latitude", "not.is.null").is_("longitude", "not.is.null")
            resp = await query.execute()
            
            # Group by rounded lat/lng
            area_counts = {}
            for row in resp.data or []:
                lat = row.get("latitude")
                lng = row.get("longitude")
                if lat is not None and lng is not None:
                    key = (round(lat, 1), round(lng, 1))
                    area_counts[key] = area_counts.get(key, 0) + 1
            
            # Sort and get top areas
            sorted_areas = sorted(area_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
            
            # Get location names by reverse geocoding (nearest location)
            areas_with_names = []
            for (lat, lng), count in sorted_areas:
                # Find nearest location from locations table
                loc_resp = await db_admin.table("locations").select("id, name, latitude, longitude").execute()
                
                nearest_loc = None
                min_dist = float('inf')
                
                for loc in loc_resp.data or []:
                    loc_lat = loc.get("latitude")
                    loc_lng = loc.get("longitude")
                    if loc_lat is not None and loc_lng is not None:
                        # Simple distance calculation
                        dist = ((loc_lat - lat) ** 2 + (loc_lng - lng) ** 2) ** 0.5
                        if dist < min_dist:
                            min_dist = dist
                            nearest_loc = loc
                
                area_name = nearest_loc.get("name") if nearest_loc else f"Area ({lat}, {lng})"
                areas_with_names.append({
                    "area_name": area_name,
                    "latitude": lat,
                    "longitude": lng,
                    "request_count": count
                })
            
            result = areas_with_names
            
        except Exception as e:
            logger.error(f"Error in area_with_most_requests: {e}")
            result = []
        
        return {
            "data": result,
            "raw_sql": raw_sql
        }

    async def _tool_query_fulfillment_rate(self, params: dict) -> dict[str, Any]:
        """
        Intent: "what is the fulfillment rate"
        Query: SELECT status, count(*) FROM resource_requests GROUP BY status
        Compute fulfilled/(total) * 100
        """
        raw_sql = """SELECT status, count(*) as count 
FROM resource_requests 
GROUP BY status"""
        
        try:
            # Get all request statuses
            resp = await db_admin.table("resource_requests").select("status").execute()
            
            status_counts = {}
            total = 0
            for row in resp.data or []:
                status = row.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
                total += 1
            
            # Calculate fulfillment rate
            fulfilled = status_counts.get("fulfilled", 0) + status_counts.get("completed", 0) + status_counts.get("approved", 0)
            fulfillment_rate = round((fulfilled / total * 100), 2) if total > 0 else 0
            
            result = {
                "status_counts": status_counts,
                "total_requests": total,
                "fulfilled_requests": fulfilled,
                "fulfillment_rate_pct": fulfillment_rate
            }
            
        except Exception as e:
            logger.error(f"Error in fulfillment_rate: {e}")
            result = {"status_counts": {}, "total_requests": 0, "fulfilled_requests": 0, "fulfillment_rate_pct": 0}
        
        return {
            "data": result,
            "raw_sql": raw_sql
        }

    async def _tool_query_active_volunteers(self, params: dict) -> dict[str, Any]:
        """
        Intent: "which volunteers are most active"
        Query: SELECT volunteer_id, count(*) FROM request_verifications 
               GROUP BY volunteer_id ORDER BY count DESC LIMIT 10
        Join with users table for names
        """
        limit = params.get("limit", 10)
        
        raw_sql = f"""SELECT rv.volunteer_id, count(*) as verification_count, u.full_name, u.email
FROM request_verifications rv
LEFT JOIN users u ON rv.volunteer_id = u.id
GROUP BY rv.volunteer_id, u.full_name, u.email
ORDER BY verification_count DESC
LIMIT {limit}"""
        
        try:
            # Get verification counts by volunteer
            resp = await db_admin.table("request_verifications").select("volunteer_id").execute()
            
            volunteer_counts = {}
            for row in resp.data or []:
                vid = row.get("volunteer_id")
                if vid:
                    volunteer_counts[vid] = volunteer_counts.get(vid, 0) + 1
            
            # Sort and get top volunteers
            sorted_volunteers = sorted(volunteer_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
            
            # Get user details for each volunteer
            top_volunteers = []
            for vid, count in sorted_volunteers:
                user_resp = await db_admin.table("users").select("id, full_name, email").eq("id", vid).execute()
                user_data = user_resp.data[0] if user_resp.data else {}
                
                top_volunteers.append({
                    "volunteer_id": vid,
                    "full_name": user_data.get("full_name", "Unknown"),
                    "email": user_data.get("email", ""),
                    "verification_count": count
                })
            
            result = top_volunteers
            
        except Exception as e:
            logger.error(f"Error in active_volunteers: {e}")
            result = []
        
        return {
            "data": result,
            "raw_sql": raw_sql
        }

    async def _tool_query_resource_shortage_prediction(self, params: dict) -> dict[str, Any]:
        """
        Intent: "predict resource shortage"
        Call the demand forecasting model (forecast_service) and return 
        the top 3 resources predicted to run short in the next 7 days
        """
        horizon_hours = params.get("horizon_hours", 168)  # 7 days = 168 hours
        
        raw_sql = "N/A - Uses forecast_service.generate_forecast()"
        
        try:
            # Get historical resource consumption data
            # Query resource_requests for consumption patterns
            since = (datetime.utcnow() - timedelta(days=30)).isoformat()  # Get last 30 days
            resp = await db_admin.table("resource_requests").select(
                "resource_type, created_at, quantity"
            ).gte("created_at", since).execute()
            
            # Aggregate by resource_type and day
            daily_consumption = {}
            for row in resp.data or []:
                rt = row.get("resource_type", "unknown")
                created = row.get("created_at")
                qty = row.get("quantity", 1)
                
                if created and rt:
                    day_key = created[:10]  # YYYY-MM-DD
                    if rt not in daily_consumption:
                        daily_consumption[rt] = {}
                    daily_consumption[rt][day_key] = daily_consumption[rt].get(day_key, 0) + qty
            
            # Get current available resources
            avail_resp = await db_admin.table("resources").select("type, quantity, status").execute()
            
            available_by_type = {}
            for row in avail_resp.data or []:
                rt = row.get("type", "unknown")
                qty = row.get("quantity", 0)
                status = row.get("status", "")
                
                if status in ["available", "allocated"]:
                    available_by_type[rt] = available_by_type.get(rt, 0) + qty
            
            # Build consumption records for forecast
            records = []
            for rt, days in daily_consumption.items():
                for day_str, qty in days.items():
                    try:
                        ts = datetime.fromisoformat(day_str)
                        avail = available_by_type.get(rt, 100)
                        records.append(ConsumptionRecord(
                            resource_type=rt,
                            timestamp=ts,
                            quantity_consumed=qty,
                            quantity_available=avail
                        ))
                    except Exception:
                        continue
            
            # Generate forecast
            if records:
                forecast_result = generate_forecast(records, horizon_hours=horizon_hours, step_hours=24)
                
                # Find top 3 resources with highest shortfall
                resource_shortages = {}
                for item in forecast_result.items:
                    if item.shortfall > 0:  # Only consider positive shortfall (shortage)
                        if item.resource_type not in resource_shortages:
                            resource_shortages[item.resource_type] = 0
                        resource_shortages[item.resource_type] = max(
                            resource_shortages[item.resource_type], 
                            item.shortfall
                        )
                
                # Sort by shortfall descending and get top 3
                sorted_shortages = sorted(
                    resource_shortages.items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:3]
                
                result = [
                    {
                        "resource_type": rt,
                        "predicted_shortfall": round(qty, 2),
                        "time_horizon_hours": horizon_hours
                    }
                    for rt, qty in sorted_shortages
                ]
            else:
                result = []
                
        except Exception as e:
            logger.error(f"Error in resource_shortage_prediction: {e}")
            result = []
        
        return {
            "data": result,
            "raw_sql": raw_sql,
            "horizon_hours": horizon_hours
        }

    async def _tool_query_today_activity_summary(self, params: dict) -> dict[str, Any]:
        """
        Intent: "summarize today's activity"
        Aggregate: new requests today, new disasters today, resources allocated today, alerts triggered today
        Return as a structured summary
        """
        raw_sql = "N/A - Multiple aggregate queries"
        
        try:
            # Get start of today
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_iso = today_start.isoformat()
            
            # New requests today
            req_resp = await db_admin.table("resource_requests").select("id").gte("created_at", today_start_iso).execute()
            new_requests_today = len(req_resp.data) if req_resp.data else 0
            
            # New disasters today
            disaster_resp = await db_admin.table("disasters").select("id").gte("created_at", today_start_iso).execute()
            new_disasters_today = len(disaster_resp.data) if disaster_resp.data else 0
            
            # Resources allocated today (status = 'allocated' or 'deployed')
            allocated_resp = await db_admin.table("resources").select("id").gte("updated_at", today_start_iso).execute()
            resources_allocated_today = 0
            for row in allocated_resp.data or []:
                # Could add more filtering if updated_at indicates allocation
                resources_allocated_today += 1
            
            # Alternative: count allocations from allocation_logs if available
            try:
                alloc_log_resp = await db_admin.table("allocation_logs").select("id").gte("created_at", today_start_iso).execute()
                resources_allocated_today = len(alloc_log_resp.data) if alloc_log_resp.data else 0
            except Exception:
                pass
            
            # Alerts triggered today
            try:
                alerts_resp = await db_admin.table("anomaly_alerts").select("id").gte("detected_at", today_start_iso).execute()
                alerts_triggered_today = len(alerts_resp.data) if alerts_resp.data else 0
            except Exception:
                alerts_triggered_today = 0
            
            result = {
                "new_requests_today": new_requests_today,
                "new_disasters_today": new_disasters_today,
                "resources_allocated_today": resources_allocated_today,
                "alerts_triggered_today": alerts_triggered_today,
                "date": datetime.utcnow().strftime("%Y-%m-%d")
            }
            
        except Exception as e:
            logger.error(f"Error in today_activity_summary: {e}")
            result = {
                "new_requests_today": 0,
                "new_disasters_today": 0,
                "resources_allocated_today": 0,
                "alerts_triggered_today": 0,
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "error": str(e)
            }
        
        return {
            "data": result,
            "raw_sql": raw_sql
        }

    async def _tool_ambiguous_id_lookup(self, params: dict) -> dict:
        """Fallback for when an ID is provided without a category keyword."""
        record_id = params.get("id")
        if not record_id:
            return {"category": "disasters", "data": []}

        # Priority tables to check
        tables = [
            ("disasters", "disasters"),
            ("resource_requests", "requests"),
            ("anomaly_alerts", "anomalies"),
            ("resources", "resources"),
            ("predictions", "predictions"),
        ]

        for table_name, category in tables:
            try:
                # Check if it's a UUID or integer based on common patterns
                resp = await db_admin.table(table_name).select("*").eq("id", record_id).async_execute()
                if resp.data:
                    return {"category": category, "data": resp.data}
            except Exception:
                continue

        return {"category": "disasters", "data": []}

    # -- Rule-based query classification and routing --

    def _classify_and_route(self, query: str) -> dict[str, Any]:
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
        for dt in [
            "earthquake",
            "flood",
            "hurricane",
            "tornado",
            "wildfire",
            "tsunami",
            "drought",
            "landslide",
            "volcano",
        ]:
            if dt in q:
                params["disaster_type"] = dt
                break

        # Priority filters
        for pri in ["critical", "high", "medium", "low"]:
            if f"{pri} priority" in q or f"priority {pri}" in q:
                params["priority"] = pri
                break

        # ========================================================
        # NEW INTENT DETECTION - Enhanced Analytics Queries
        # ========================================================

        # Intent: "how many [resource_type] requests in the last [N] days"
        # Match patterns like: "how many food requests in the last 7 days"
        if any(w in q for w in ["how many"]) and any(w in q for w in ["request"]) and any(w in q for w in ["last", "past", "days"]):
            # Extract resource type
            for rt in ["food", "water", "medical", "shelter", "clothing", "medicine", " blankets", "tents"]:
                if rt in q:
                    params["resource_type"] = rt.strip()
                    break
            # Extract number of days
            day_match = re.search(r"(\d+)\s*(?:days|day)", q)
            if day_match:
                params["days"] = int(day_match.group(1))
            else:
                params["days"] = 7  # Default to 7 days
            return {"tool": "resource_requests_by_type_and_time", "params": params, "category": "resource_requests_count"}

        # Intent: "which area has the most requests"
        if any(w in q for w in ["area", "location", "region", "place"]) and any(w in q for w in ["most", "highest", "top"]) and any(w in q for w in ["request", "cases"]):
            return {"tool": "area_with_most_requests", "params": params, "category": "area_requests"}

        # Intent: "what is the fulfillment rate"
        if any(w in q for w in ["fulfillment", "fulfilment", "fulfilled", "completion", "completion rate"]) and any(w in q for w in ["rate", "percentage"]):
            return {"tool": "fulfillment_rate", "params": params, "category": "fulfillment"}

        # Intent: "which volunteers are most active"
        if any(w in q for w in ["volunteer", "volunteers"]) and any(w in q for w in ["active", "most", "top"]):
            return {"tool": "active_volunteers", "params": params, "category": "active_volunteers"}

        # Intent: "predict resource shortage" or "forecast shortage"
        if any(w in q for w in ["predict", "forecast", "shortage", "shortfall", "run short", "running out"]) and any(w in q for w in ["resource", "supply"]):
            params["horizon_hours"] = 168  # 7 days
            return {"tool": "resource_shortage_prediction", "params": params, "category": "shortage_prediction"}

        # Intent: "summarize today's activity" or "daily summary"
        if any(w in q for w in ["summarize", "summary", "today", "daily", "today's", "overview"]) and any(w in q for w in ["activity", "status", "overview"]):
            return {"tool": "today_activity_summary", "params": params, "category": "daily_summary"}

        # ========================================================
        # END NEW INTENT DETECTION
        # ========================================================

        # Route to the right tool based on keywords

        # ID-based lookup priority
        id_match = re.search(r"(?:disaster|request|prediction|report|alert|anomaly|resource)\s*#?\s*([a-f0-9-]{8,})", q)
        if not id_match:
            id_match = re.search(r"#\s*(\d+)", q)  # Simple #123 matches
        if not id_match:
            # Catch-all for UUID-like strings
            id_match = re.search(r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", q)

        if id_match:
            record_id = id_match.group(1)
            params["id"] = record_id
            if "disaster" in q:
                return {"tool": "disasters", "params": params, "category": "disasters"}
            if "request" in q:
                return {"tool": "victim_requests", "params": params, "category": "requests"}
            if "prediction" in q:
                return {"tool": "predictions", "params": params, "category": "predictions"}
            if "alert" in q or "anomaly" in q:
                return {"tool": "anomaly_alerts", "params": params, "category": "anomalies"}
            if "resource" in q:
                return {"tool": "resources", "params": params, "category": "resources"}

            # If no keyword found but ID exists, use ambiguous lookup
            return {"tool": "ambiguous_id", "params": params, "category": "ambiguous"}

        if any(w in q for w in ["anomal", "unusual", "spike", "unexpected", "weird"]):
            return {"tool": "anomaly_alerts", "params": params, "category": "anomalies"}
        if any(w in q for w in ["predict", "forecast", "ml ", "model", "confidence"]):
            params.setdefault("since_hours", 48)
            return {"tool": "predictions", "params": params, "category": "predictions"}
        if any(w in q for w in ["outcome", "accuracy", "actual vs", "performance"]):
            return {"tool": "outcome_tracking", "params": params, "category": "outcomes"}
        if any(w in q for w in ["utiliz", "allocation", "how much resource", "resource status"]):
            return {"tool": "resource_utilization", "params": params, "category": "utilization"}
        if any(
            w in q
            for w in ["available resource", "inventory", "stock", "supply available", "what's available", "remaining"]
        ):
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
            params.update({"since_hours": 24})
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
                    lines.append("| Status | Count |")
                    lines.append("|--------|-------|")
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
            lines.append("| Title | Severity | Type | Status | Affected |")
            lines.append("|-------|----------|------|--------|----------|")
            for d in data[:15]:
                sev = d.get("severity", "?").upper()
                pop = f"{d['affected_population']:,}" if d.get("affected_population") else "-"
                lines.append(
                    f"| {d.get('title', 'Untitled')} | {sev} | {d.get('type', '?')} | {d.get('status', '?')} | {pop} |"
                )
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
                lines.append(
                    f"| {r.get('category', '?')} | {r.get('title', '?')} | {remaining}/{total} | {r.get('unit', 'units')} |"
                )
            return "\n".join(lines)

        if category == "requests":
            lines = [f"## Victim Requests ({count} found)\n"]
            lines.append("| Resource | Priority | Status | Qty |")
            lines.append("|----------|----------|--------|-----|")
            for r in data[:20]:
                lines.append(
                    f"| {r.get('resource_type', '?')} | {r.get('priority', '?')} | {r.get('status', '?')} | {r.get('quantity', 1)} |"
                )
            return "\n".join(lines)

        if category == "predictions":
            lines = [f"## Predictions ({count} found)\n"]
            lines.append("| Type | Severity | Confidence | Created |")
            lines.append("|------|----------|------------|---------|")
            for p in data[:15]:
                conf = p.get("confidence_score", 0)
                conf_str = f"{conf:.1%}" if isinstance(conf, (int, float)) else str(conf)
                created_at = str(p.get("created_at", ""))
                created_at_short = created_at[0:16] if len(created_at) >= 16 else created_at
                lines.append(
                    f"| {p.get('prediction_type', '?')} | {p.get('predicted_severity', '-')} | {conf_str} | {created_at_short} |"
                )
            return "\n".join(lines)

        if category == "anomalies":
            lines = [f"## Anomaly Alerts ({count} found)\n"]
            lines.append("| Severity | Title | Type | Explanation |")
            lines.append("|----------|-------|------|-------------|")
            for a in data[:10]:
                expl = (
                    (a.get("ai_explanation") or "")[:100] + "..."
                    if len(a.get("ai_explanation") or "") > 100
                    else a.get("ai_explanation", "")
                )
                lines.append(
                    f"| {a.get('severity', '?').upper()} | {a.get('title', 'Unknown')} | {a.get('anomaly_type', '')} | {expl} |"
                )
            return "\n".join(lines)

        if category == "ingestion":
            lines = [f"## Ingested Events ({count} found)\n"]
            lines.append("| Type | Title | Severity | Processed |")
            lines.append("|------|-------|----------|-----------|")
            for e in data[:20]:
                title_short = (e.get("title") or "")[:50]
                lines.append(
                    f"| {e.get('event_type', '?')} | {title_short} | {e.get('severity', '?')} | {'Yes' if e.get('processed') else 'No'} |"
                )
            return "\n".join(lines)

        if category == "outcomes":
            lines = [f"## Outcome Tracking ({count} found)\n"]
            for o in data[:10]:
                lines.append(
                    f"- **{o.get('prediction_type', '?')}**: predicted={o.get('predicted_severity', '?')} actual={o.get('actual_severity', '?')} match={o.get('severity_match', '?')}"
                )
            return "\n".join(lines)

        if category == "users":
            lines = [f"## Users ({count} found)\n"]
            lines.append("| Name | Email | Role | Joined |")
            lines.append("|------|-------|------|--------|")
            for u in data[:20]:
                created_at = str(u.get("created_at", ""))
                created_at_short = created_at[0:10] if len(created_at) >= 10 else created_at
                lines.append(
                    f"| {u.get('full_name', '?')} | {u.get('email', '?')} | {u.get('role', '?')} | {created_at_short} |"
                )
            return "\n".join(lines)

        # ========================================================
        # NEW CATEGORY FORMATTERS - Enhanced Analytics
        # ========================================================

        # Category: resource_requests_count - "how many [resource_type] requests in the last [N] days"
        if category == "resource_requests_count":
            if isinstance(data, dict):
                items = data.get("data", [])
                days = data.get("days", 7)
                resource_type = data.get("resource_type", "")
            else:
                items = data if isinstance(data, list) else []
                days = 7
                resource_type = ""
            
            lines = [f"## Resource Requests Count (Last {days} days)\n"]
            if resource_type:
                lines.append(f"*Filter: {resource_type}*\n")
            lines.append("| Resource Type | Count |")
            lines.append("|--------------|-------|")
            for item in items:
                lines.append(f"| {item.get('resource_type', '?')} | {item.get('count', 0)} |")
            return "\n".join(lines)

        # Category: area_requests - "which area has the most requests"
        if category == "area_requests":
            if isinstance(data, dict):
                items = data.get("data", [])
            else:
                items = data if isinstance(data, list) else []
            
            lines = ["## Top Areas with Most Requests\n"]
            lines.append("| Area Name | Request Count |")
            lines.append("|------------|----------------|")
            for item in items:
                lines.append(f"| {item.get('area_name', '?')} | {item.get('request_count', 0)} |")
            return "\n".join(lines)

        # Category: fulfillment - "what is the fulfillment rate"
        if category == "fulfillment":
            if isinstance(data, dict):
                result = data
            else:
                result = {"fulfillment_rate_pct": 0}
            
            lines = ["## Fulfillment Rate\n"]
            lines.append(f"- **Total Requests:** {result.get('total_requests', 0)}")
            lines.append(f"- **Fulfilled:** {result.get('fulfilled_requests', 0)}")
            lines.append(f"- **Fulfillment Rate:** {result.get('fulfillment_rate_pct', 0)}%\n")
            
            status_counts = result.get("status_counts", {})
            if status_counts:
                lines.append("| Status | Count |")
                lines.append("|--------|-------|")
                for s, c in sorted(status_counts.items()):
                    lines.append(f"| {s} | {c} |")
            return "\n".join(lines)

        # Category: active_volunteers - "which volunteers are most active"
        if category == "active_volunteers":
            if isinstance(data, dict):
                items = data.get("data", [])
            else:
                items = data if isinstance(data, list) else []
            
            lines = ["## Most Active Volunteers\n"]
            lines.append("| Rank | Name | Email | Verifications |")
            lines.append("|------|------|-------|----------------|")
            for i, item in enumerate(items, 1):
                lines.append(f"| {i} | {item.get('full_name', '?')} | {item.get('email', '?')} | {item.get('verification_count', 0)} |")
            return "\n".join(lines)

        # Category: shortage_prediction - "predict resource shortage"
        if category == "shortage_prediction":
            if isinstance(data, dict):
                items = data.get("data", [])
                horizon = data.get("horizon_hours", 168)
            else:
                items = data if isinstance(data, list) else []
                horizon = 168
            
            days = horizon // 24
            lines = [f"## Predicted Resource Shortages (Next {days} days)\n"]
            
            if not items:
                lines.append("No resource shortages predicted based on current trends.\n")
                return "\n".join(lines)
            
            lines.append("| Resource Type | Predicted Shortfall |")
            lines.append("|---------------|---------------------|")
            for item in items:
                shortfall = item.get('predicted_shortfall', 0)
                lines.append(f"| {item.get('resource_type', '?')} | {shortfall:,.0f} |")
            lines.append("\n*Based on demand forecasting model using historical consumption data.*")
            return "\n".join(lines)

        # Category: daily_summary - "summarize today's activity"
        if category == "daily_summary":
            if isinstance(data, dict):
                result = data
            else:
                result = {}
            
            lines = ["## Today's Activity Summary\n"]
            date_str = result.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
            lines.append(f"**Date:** {date_str}\n")
            lines.append(f"- **New Requests:** {result.get('new_requests_today', 0)}")
            lines.append(f"- **New Disasters:** {result.get('new_disasters_today', 0)}")
            lines.append(f"- **Resources Allocated:** {result.get('resources_allocated_today', 0)}")
            lines.append(f"- **Alerts Triggered:** {result.get('alerts_triggered_today', 0)}")
            return "\n".join(lines)

        # ========================================================
        # END NEW CATEGORY FORMATTERS
        # ========================================================

        # Fallback: just dump JSON
        return f"Found {count} result(s):\n`json\n{json.dumps(data[:5], indent=2, default=str)}\n`"

    # -- Groq LLM Enhancement --

    async def _generate_llm_response(self, query: str, category: str, data: Any, rule_based_text: str) -> str:
        """Use Groq API to generate a more intelligent, natural response."""
        if not _llm_available or not _llm_client:
            return rule_based_text

        logger.info(f"Generating LLM response ({_llm_provider}) for query: '{query[:50]}...'")
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
            def call_groq():
                return _llm_client.chat.completions.create(
                    model=_llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=1024,
                    temperature=0.7,
                )

            response = await loop.run_in_executor(None, call_groq)
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
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Process a natural language query using rule-based routing + optional Groq LLM."""
        start_ms = time.time()

        # Classify and route the query
        route = self._classify_and_route(query_text)
        tool_name = str(route.get("tool", "unknown"))
        params = dict[str, Any](route.get("params", {}))
        category = str(route.get("category", "general"))

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
                "ambiguous_id": self._tool_ambiguous_id_lookup,
                # New analytics tools
                "resource_requests_by_type_and_time": self._tool_query_resource_requests_by_type_and_time,
                "area_with_most_requests": self._tool_query_area_with_most_requests,
                "fulfillment_rate": self._tool_query_fulfillment_rate,
                "active_volunteers": self._tool_query_active_volunteers,
                "resource_shortage_prediction": self._tool_query_resource_shortage_prediction,
                "today_activity_summary": self._tool_query_today_activity_summary,
            }
            fn = dispatch.get(tool_name)
            if fn:
                res = await fn(params)
                # Handle new tool responses that return dicts with "data" and "raw_sql"
                if isinstance(res, dict) and "data" in res:
                    data = res.get("data", [])
                    raw_sql = res.get("raw_sql", "")
                    tools_called[0]["raw_sql"] = raw_sql
                    if tool_name == "ambiguous_id" and isinstance(res, dict):
                        category = res.get("category", category)
                elif tool_name == "ambiguous_id" and isinstance(res, dict):
                    data = res.get("data", [])
                    category = res.get("category", category)
                else:
                    data = res
                tools_called[0]["result_count"] = len(data) if isinstance(data, (list, dict)) else 1
            else:
                data = []
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            data = []
            tools_called[0]["error"] = str(e)

        # Format the response (rule-based first)
        rule_based_text = self._format_response(category, data, query_text)

        # Enhance with LLM if available (Groq)
        if _llm_available:
            response_text = await self._generate_llm_response(query_text, category, data, rule_based_text)
            model_used = _llm_model
        else:
            response_text = rule_based_text
            model_used = "rule-based"

        latency_ms = int((time.time() - start_ms) * 1000)

        # Extract raw_sql from tools_called for logging
        raw_sql_log = ""
        for tool_call in tools_called:
            if "raw_sql" in tool_call:
                raw_sql_log = tool_call.get("raw_sql", "")
                break

        # Log to database
        log_record = {
            "user_id": user_id,
            "session_id": session_id,
            "query_text": query_text,
            "query_type": category,
            "tools_called": tools_called,
            "response_text": response_text,
            "response_data": {
                "raw_sql": raw_sql_log,
                "data": data if not isinstance(data, str) else {}
            },
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
            "raw_sql": raw_sql_log,  # Include raw SQL for admin transparency
        }

    def _classify_query(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["chart", "graph", "plot", "visualize", "trend"]):
            return "chart"
        if any(w in q for w in ["recommend", "suggest", "should", "what to do"]):
            return "recommendation"
        if any(w in q for w in ["compare", "vs", "versus", "difference", "between"]):
            return "analysis"
        return "data_query"

    # -- Query log retrieval --

    async def get_query_history(
        self, user_id: str | None = None, session_id: str | None = None, limit: int = 20
    ) -> list[dict]:
        query = (
            db_admin.table("nl_query_log")
            .select(
                "id, query_text, query_type, response_text, tools_called, latency_ms, feedback_rating, model_used, created_at"
            )
            .order("created_at", desc=True)
            .limit(limit)
        )
        if user_id:
            query = query.eq("user_id", user_id)
        if session_id:
            query = query.eq("session_id", session_id)
        resp = await query.async_execute()
        return resp.data or []

    async def submit_feedback(self, query_id: str, rating: int) -> bool:
        try:
            await db_admin.table("nl_query_log").update({"feedback_rating": rating}).eq("id", query_id).async_execute()
            return True
        except Exception as e:
            logger.error(f"Failed to submit feedback: {e}")
            return False
