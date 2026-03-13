"""
AI-Powered Insights Service for Admin Dashboard

This service provides comprehensive AI-driven analytics and insights by analyzing:
- Victim-generated submissions and resource requests
- User interactions and verification patterns
- Resource allocation patterns and outcomes
- Disaster trends and predictions
- Platform health metrics

Features include:
- Pattern detection and anomaly identification
- Trend analysis and forecasting
- Sentiment analysis from victim submissions
- Resource optimization recommendations
- Fairness and bias monitoring
- Privacy-preserving data aggregation
"""

import logging
import traceback
from datetime import UTC, datetime, timedelta
from typing import Any
from collections import defaultdict
import json
import statistics

from app.database import db_admin

logger = logging.getLogger(__name__)


class AIInsightsService:
    """
    Service for generating AI-powered insights from platform data.
    Designed for admin dashboard consumption with privacy protection.
    """

    def __init__(self):
        self.cache_ttl = 300  # 5 minutes cache for expensive queries

    # ─────────────────────────────────────────────────────────────
    # VICTIM INSIGHTS - Analyze victim-generated submissions
    # ─────────────────────────────────────────────────────────────

    async def get_victim_submission_insights(self, days: int = 30) -> dict[str, Any]:
        """
        Analyze victim submissions to identify patterns, needs, and trends.
        """
        try:
            since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

            # Get victim resource requests
            requests_resp = (
                await db_admin.table("resource_requests")
                .select("""
                    id, created_at, status, priority, resource_type,
                    quantity, latitude, longitude, nlp_classification,
                    urgency_signals, extracted_needs
                """)
                .gte("created_at", since)
                .limit(5000)
                .async_execute()
            )
            requests = requests_resp.data or []

            # Analyze patterns
            insights = {
                "total_submissions": len(requests),
                "submission_trends": self._analyze_submission_trends(requests),
                "resource_needs_breakdown": self._analyze_resource_needs(requests),
                "priority_distribution": self._analyze_priority_distribution(requests),
                "geographic_hotspots": self._analyze_geographic_distribution(requests),
                "urgent_needs": self._identify_urgent_needs(requests),
                "nlp_analysis": self._analyze_nlp_classifications(requests),
            }

            return insights

        except Exception as e:
            logger.error(f"Error generating victim insights: {e}")
            traceback.print_exc()
            return {"error": str(e)}

    def _analyze_submission_trends(self, requests: list[dict]) -> dict:
        """Analyze submission volume over time."""
        daily_counts = defaultdict(int)
        for req in requests:
            day = req.get("created_at", "")[:10]
            daily_counts[day] += 1

        # Calculate trend
        sorted_days = sorted(daily_counts.items())
        if len(sorted_days) >= 7:
            recent_week = sum(c for _, c in sorted_days[-7:])
            prev_week = sum(c for _, c in sorted_days[-14:-7]) if len(sorted_days) >= 14 else recent_week
            trend = "increasing" if recent_week > prev_week * 1.1 else "decreasing" if recent_week < prev_week * 0.9 else "stable"
        else:
            trend = "insufficient_data"

        return {
            "daily_breakdown": dict(sorted_days),
            "trend": trend,
            "avg_daily": round(len(requests) / max(len(sorted_days), 1), 1),
        }

    def _analyze_resource_needs(self, requests: list[dict]) -> dict:
        """Analyze resource type distribution."""
        type_counts = defaultdict(int)
        for req in requests:
            rt = req.get("resource_type", "unknown")
            type_counts[rt] += 1

        total = len(requests) if requests else 1
        return {
            type_: {
                "count": count,
                "percentage": round(count / total * 100, 1)
            }
            for type_, count in type_counts.items()
        }

    def _analyze_priority_distribution(self, requests: list[dict]) -> dict:
        """Analyze priority level distribution."""
        priority_counts = defaultdict(int)
        for req in requests:
            priority = req.get("priority", 5)
            priority_counts[priority] += 1

        return {
            "distribution": dict(priority_counts),
            "high_priority_count": sum(c for p, c in priority_counts.items() if p <= 2),
            "avg_priority": round(sum(p * c for p, c in priority_counts.items()) / max(sum(priority_counts.values()), 1), 2),
        }

    def _analyze_geographic_distribution(self, requests: list[dict]) -> list[dict]:
        """Identify geographic hotspots using simple clustering."""
        location_buckets = defaultdict(lambda: {"count": 0, "lat_sum": 0, "lng_sum": 0})

        for req in requests:
            lat = req.get("latitude")
            lng = req.get("longitude")
            if lat and lng:
                # Bucket into ~10km grid cells
                bucket_lat = round(lat, 1)
                bucket_lng = round(lng, 1)
                key = f"{bucket_lat}_{bucket_lng}"
                location_buckets[key]["count"] += 1
                location_buckets[key]["lat_sum"] += lat
                location_buckets[key]["lng_sum"] += lng

        # Convert to sorted list
        hotspots = []
        for key, data in location_buckets.items():
            if data["count"] >= 3:  # Minimum threshold
                hotspots.append({
                    "region": key,
                    "count": data["count"],
                    "avg_lat": round(data["lat_sum"] / data["count"], 4),
                    "avg_lng": round(data["lng_sum"] / data["count"], 4),
                })

        return sorted(hotspots, key=lambda x: x["count"], reverse=True)[:10]

    def _identify_urgent_needs(self, requests: list[dict]) -> list[dict]:
        """Identify the most urgent pending needs."""
        urgent = []
        for req in requests:
            if req.get("status") in ("pending", "in_progress") and req.get("priority", 5) <= 2:
                urgent.append({
                    "request_id": req.get("id"),
                    "resource_type": req.get("resource_type"),
                    "priority": req.get("priority"),
                    "created_at": req.get("created_at"),
                    "days_pending": (datetime.now(UTC) - datetime.fromisoformat(req.get("created_at", "").replace("+00:00", "Z"))).days,
                })

        return sorted(urgent, key=lambda x: (x["priority"], -x["days_pending"]))[:20]

    def _analyze_nlp_classifications(self, requests: list[dict]) -> dict:
        """Analyze NLP classifications from victim submissions."""
        categories = defaultdict(int)
        sentiment_scores = []

        for req in requests:
            nlp = req.get("nlp_classification")
            if isinstance(nlp, str):
                try:
                    nlp = json.loads(nlp)
                except:
                    nlp = None

            if nlp and isinstance(nlp, dict):
                primary = nlp.get("primary_category", "unknown")
                categories[primary] += 1

                sentiment = nlp.get("sentiment_score", 0)
                if sentiment:
                    sentiment_scores.append(sentiment)

        return {
            "category_distribution": dict(categories),
            "avg_sentiment": round(sum(sentiment_scores) / max(len(sentiment_scores), 1), 2) if sentiment_scores else 0,
            "sentiment_trend": "negative" if sum(sentiment_scores) / max(len(sentiment_scores), 1) < -0.2 else "neutral" if sum(sentiment_scores) / max(len(sentiment_scores), 1) < 0.2 else "positive",
        }

    # ─────────────────────────────────────────────────────────────
    # PLATFORM HEALTH INSIGHTS
    # ─────────────────────────────────────────────────────────────

    async def get_platform_health_insights(self) -> dict[str, Any]:
        """
        Generate comprehensive platform health metrics and insights.
        """
        try:
            # Get key metrics
            disasters_resp = (
                await db_admin.table("disasters")
                .select("id, status, severity, type")
                .limit(1000)
                .async_execute()
            )
            disasters = disasters_resp.data or []

            requests_resp = (
                await db_admin.table("resource_requests")
                .select("id, status, created_at")
                .limit(5000)
                .async_execute()
            )
            requests = requests_resp.data or []

            verif_resp = (
                await db_admin.table("request_verifications")
                .select("id, verification_status")
                .limit(5000)
                .async_execute()
            )
            verifications = verif_resp.data or []

            return {
                "disaster_overview": {
                    "active": len([d for d in disasters if d.get("status") == "active"]),
                    "monitoring": len([d for d in disasters if d.get("status") == "monitoring"]),
                    "resolved": len([d for d in disasters if d.get("status") == "resolved"]),
                    "severity_breakdown": self._get_severity_breakdown(disasters),
                    "type_distribution": self._get_disaster_type_breakdown(disasters),
                },
                "request_pipeline": {
                    "total": len(requests),
                    "pending": len([r for r in requests if r.get("status") == "pending"]),
                    "in_progress": len([r for r in requests if r.get("status") == "in_progress"]),
                    "completed": len([r for r in requests if r.get("status") in ("completed", "delivered", "satisfied")]),
                    "fulfillment_rate": round(len([r for r in requests if r.get("status") in ("completed", "delivered", "satisfied")]) / max(len(requests), 1) * 100, 1),
                },
                "verification_quality": {
                    "total": len(verifications),
                    "trusted": len([v for v in verifications if v.get("verification_status") == "trusted"]),
                    "false_alarms": len([v for v in verifications if v.get("verification_status") == "false_alarm"]),
                    "dubious": len([v for v in verifications if v.get("verification_status") == "dubious"]),
                    "accuracy_rate": round(len([v for v in verifications if v.get("verification_status") == "trusted"]) / max(len(verifications), 1) * 100, 1),
                },
                "health_score": self._calculate_platform_health_score(disasters, requests, verifications),
            }

        except Exception as e:
            logger.error(f"Error generating platform health: {e}")
            traceback.print_exc()
            return {"error": str(e)}

    def _get_severity_breakdown(self, disasters: list[dict]) -> dict:
        return {s: len([d for d in disasters if d.get("severity") == s]) for s in ["low", "medium", "high", "critical"]}

    def _get_disaster_type_breakdown(self, disasters: list[dict]) -> dict:
        types = defaultdict(int)
        for d in disasters:
            types[d.get("type", "unknown")] += 1
        return dict(types)

    def _calculate_platform_health_score(self, disasters: list[dict], requests: list[dict], verifications: list[dict]) -> int:
        """Calculate a 0-100 health score for the platform."""
        score = 100

        # Penalize for critical disasters
        critical_count = len([d for d in disasters if d.get("severity") == "critical" and d.get("status") == "active"])
        score -= min(critical_count * 10, 30)

        # Penalize for high pending request ratio
        if requests:
            pending_ratio = len([r for r in requests if r.get("status") == "pending"]) / len(requests)
            score -= min(int(pending_ratio * 20), 20)

        # Penalize for low verification accuracy
        if verifications:
            accuracy = len([v for v in verifications if v.get("verification_status") == "trusted"]) / len(verifications)
            if accuracy < 0.7:
                score -= 15

        return max(score, 0)

    # ─────────────────────────────────────────────────────────────
    # TREND ANALYSIS & FORECASTING
    # ─────────────────────────────────────────────────────────────

    async def get_trend_forecasts(self, metric: str, days_ahead: int = 7) -> dict[str, Any]:
        """
        Generate simple trend forecasts for key metrics.
        Uses moving averages and linear extrapolation.
        """
        try:
            if metric == "requests":
                return await self._forecast_request_volume(days_ahead)
            elif metric == "resources":
                return await self._forecast_resource_demand(days_ahead)
            elif metric == "disasters":
                return await self._forecast_disaster_activity(days_ahead)
            else:
                return {"error": f"Unknown metric: {metric}"}

        except Exception as e:
            logger.error(f"Error generating forecast: {e}")
            return {"error": str(e)}

    async def _forecast_request_volume(self, days_ahead: int) -> dict:
        """Forecast request volume using simple moving average."""
        # Get last 30 days of data
        since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        resp = (
            await db_admin.table("resource_requests")
            .select("created_at")
            .gte("created_at", since)
            .limit(5000)
            .async_execute()
        )
        requests = resp.data or []

        # Group by day
        daily = defaultdict(int)
        for req in requests:
            day = req.get("created_at", "")[:10]
            daily[day] += 1

        sorted_days = sorted(daily.items())
        if len(sorted_days) < 7:
            return {"error": "Insufficient data for forecasting"}

        # Calculate 7-day moving average
        values = [c for _, c in sorted_days]
        ma_7 = sum(values[-7:]) / 7

        # Simple trend detection
        recent_avg = sum(values[-7:]) / 7
        prev_avg = sum(values[-14:-7]) / 7 if len(values) >= 14 else recent_avg
        trend_pct = ((recent_avg - prev_avg) / max(prev_avg, 1)) * 100

        # Forecast
        forecast = []
        current = recent_avg
        for i in range(1, days_ahead + 1):
            # Apply dampened trend
            current = current * (1 + (trend_pct / 100) * 0.5)
            forecast.append({
                "day": i,
                "predicted_requests": round(current),
            })

        return {
            "historical": dict(sorted_days[-14:]),
            "moving_average_7d": round(ma_7, 1),
            "trend": "increasing" if trend_pct > 5 else "decreasing" if trend_pct < -5 else "stable",
            "trend_percentage": round(trend_pct, 1),
            "forecast": forecast,
            "confidence": "medium" if len(sorted_days) >= 21 else "low",
        }

    async def _forecast_resource_demand(self, days_ahead: int) -> dict:
        """Forecast resource demand by type."""
        since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        resp = (
            await db_admin.table("resource_requests")
            .select("resource_type, quantity, created_at")
            .gte("created_at", since)
            .limit(5000)
            .async_execute()
        )
        requests = resp.data or []

        # Group by type and day
        by_type = defaultdict(lambda: defaultdict(int))
        for req in requests:
            rt = req.get("resource_type", "unknown")
            day = req.get("created_at", "")[:10]
            by_type[rt][day] += req.get("quantity", 1)

        forecast = {}
        for rt, daily_data in by_type.items():
            sorted_days = sorted(daily_data.items())
            if len(sorted_days) >= 7:
                avg = sum(c for _, c in sorted_days[-7:]) / 7
                forecast[rt] = {
                    "avg_daily": round(avg, 1),
                    "predicted_daily": round(avg * 1.1),  # Simple 10% growth assumption
                }

        return {"resource_forecasts": forecast}

    async def _forecast_disaster_activity(self, days_ahead: int) -> dict:
        """Forecast expected disaster activity."""
        # Get recent disasters
        since = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        resp = (
            await db_admin.table("disasters")
            .select("created_at, type, severity")
            .gte("created_at", since)
            .limit(500)
            .async_execute()
        )
        disasters = resp.data or []

        # Calculate average disasters per week
        if disasters:
            weekly_avg = len(disasters) / 8  # ~8 weeks
            return {
                "current_active": len([d for d in disasters if d.get("status") == "active"]),
                "weekly_average": round(weekly_avg, 1),
                "forecast_weekly": round(weekly_avg * 1.1),
                "high_risk_types": self._get_high_risk_types(disasters),
            }

        return {"message": "Insufficient disaster data"}

    def _get_high_risk_types(self, disasters: list[dict]) -> list[dict]:
        """Identify disaster types with highest frequency."""
        type_counts = defaultdict(int)
        for d in disasters:
            type_counts[d.get("type", "unknown")] += 1

        return sorted(
            [{"type": t, "count": c} for t, c in type_counts.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:3]

    # ─────────────────────────────────────────────────────────────
    # RESOURCE OPTIMIZATION RECOMMENDATIONS
    # ─────────────────────────────────────────────────────────────

    async def get_resource_optimization_insights(self) -> dict[str, Any]:
        """
        Generate resource allocation and optimization recommendations.
        """
        try:
            # Get resource requests and allocations
            requests_resp = (
                await db_admin.table("resource_requests")
                .select("id, resource_type, quantity, status, assigned_to, priority")
                .limit(5000)
                .async_execute()
            )
            requests = requests_resp.data or []

            # Get available resources
            resources_resp = (
                await db_admin.table("resources")
                .select("id, resource_type, total_quantity, status, location_id")
                .limit(2000)
                .async_execute()
            )
            resources = resources_resp.data or []

            # Analyze gaps
            needed = defaultdict(lambda: {"total_needed": 0, "fulfilled": 0, "pending": 0})
            for req in requests:
                rt = req.get("resource_type", "unknown")
                needed[rt]["total_needed"] += req.get("quantity", 1)
                if req.get("status") in ("completed", "delivered", "satisfied"):
                    needed[rt]["fulfilled"] += req.get("quantity", 1)
                elif req.get("status") == "pending":
                    needed[rt]["pending"] += req.get("quantity", 1)

            # Analyze available supply
            available = defaultdict(float)
            for res in resources:
                if res.get("status") == "available":
                    available[res.get("resource_type", "unknown")] += res.get("total_quantity", 0)

            # Generate recommendations
            recommendations = []
            for rt, data in needed.items():
                supply = available.get(rt, 0)
                demand = data["pending"]
                if demand > supply:
                    recommendations.append({
                        "resource_type": rt,
                        "shortage": round(demand - supply),
                        "urgency": "high" if data["pending"] > data["fulfilled"] * 0.5 else "medium",
                        "recommendation": f"Procure additional {rt} supplies or activate emergency procurement channels",
                    })

            # Sort by shortage severity
            recommendations.sort(key=lambda x: x["shortage"], reverse=True)

            return {
                "demand_analysis": {rt: {
                    "total_needed": d["total_needed"],
                    "fulfilled": d["fulfilled"],
                    "pending": d["pending"],
                    "fulfillment_rate": round(d["fulfilled"] / max(d["total_needed"], 1) * 100, 1)
                } for rt, d in needed.items()},
                "supply_gap_recommendations": recommendations[:10],
                "allocation_efficiency": self._calculate_allocation_efficiency(requests),
            }

        except Exception as e:
            logger.error(f"Error generating optimization insights: {e}")
            return {"error": str(e)}

    def _calculate_allocation_efficiency(self, requests: list[dict]) -> dict:
        """Calculate resource allocation efficiency metrics."""
        if not requests:
            return {"efficiency_score": 0, "message": "No data"}

        assigned = len([r for r in requests if r.get("assigned_to")])
        total = len(requests)

        return {
            "efficiency_score": round(assigned / max(total, 1) * 100, 1),
            "assigned_count": assigned,
            "unassigned_count": total - assigned,
            "status": "optimal" if assigned / max(total, 1) > 0.8 else "needs_improvement",
        }

    # ─────────────────────────────────────────────────────────────
    # ANOMALY DETECTION FOR ADMIN ATTENTION
    # ─────────────────────────────────────────────────────────────

    async def get_anomaly_insights(self) -> dict[str, Any]:
        """
        Detect anomalies in platform data that require admin attention.
        """
        try:
            anomalies = []

            # Check for unusual request patterns
            since = (datetime.now(UTC) - timedelta(days=7)).isoformat()
            resp = (
                await db_admin.table("resource_requests")
                .select("created_at, priority, status")
                .gte("created_at", since)
                .limit(5000)
                .async_execute()
            )
            requests = resp.data or []

            # Detect priority 1 requests not addressed in 24h
            for req in requests:
                if req.get("priority") == 1 and req.get("status") == "pending":
                    created = datetime.fromisoformat(req.get("created_at", "").replace("+00:00", "Z"))
                    hours_pending = (datetime.now(UTC) - created).total_seconds() / 3600
                    if hours_pending > 24:
                        anomalies.append({
                            "type": "urgent_request_stuck",
                            "request_id": req.get("id"),
                            "hours_pending": round(hours_pending, 1),
                            "severity": "critical",
                            "message": f"Priority 1 request pending for {round(hours_pending, 1)} hours",
                        })

            # Check for resource type spikes
            type_counts = defaultdict(int)
            for req in requests:
                type_counts[req.get("resource_type", "unknown")] += 1

            avg_count = len(requests) / max(len(type_counts), 1)
            for rt, count in type_counts.items():
                if count > avg_count * 3:
                    anomalies.append({
                        "type": "unusual_demand_spike",
                        "resource_type": rt,
                        "count": count,
                        "severity": "warning",
                        "message": f"Unusually high demand for {rt}: {count} requests (avg: {round(avg_count, 1)})",
                    })

            # Check verification backlogs
            verif_resp = (
                await db_admin.table("request_verifications")
                .select("id, created_at, verification_status")
                .eq("verification_status", "pending")
                .limit(1000)
                .async_execute()
            )
            pending_verifs = verif_resp.data or []

            if len(pending_verifs) > 50:
                anomalies.append({
                    "type": "verification_backlog",
                    "count": len(pending_verifs),
                    "severity": "warning",
                    "message": f"Large verification backlog: {len(pending_verifs)} pending verifications",
                })

            return {
                "anomalies_detected": len(anomalies),
                "critical_count": len([a for a in anomalies if a.get("severity") == "critical"]),
                "warning_count": len([a for a in anomalies if a.get("severity") == "warning"]),
                "anomalies": sorted(anomalies, key=lambda x: {"critical": 0, "warning": 1, "info": 2}.get(x.get("severity", "info"), 2)),
            }

        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
            return {"error": str(e)}

    # ─────────────────────────────────────────────────────────────
    # FAIRNESS & BIAS MONITORING
    # ─────────────────────────────────────────────────────────────

    async def get_fairness_insights(self) -> dict[str, Any]:
        """
        Monitor fairness metrics to ensure equitable resource allocation.
        Privacy-preserving: uses aggregated data only, no individual PII.
        """
        try:
            # Get resource allocation data
            requests_resp = (
                await db_admin.table("resource_requests")
                .select("id, resource_type, priority, status, latitude, longitude")
                .limit(5000)
                .async_execute()
            )
            requests = requests_resp.data or []

            # Analyze by geographic regions (privacy-preserving)
            regions = defaultdict(lambda: {"total": 0, "fulfilled": 0, "pending": 0})
            for req in requests:
                lat = req.get("latitude")
                lng = req.get("longitude")
                if lat and lng:
                    # Simple region bucketing (roughly 100km cells)
                    region = f"{round(lat, 1)}_{round(lng, 1)}"
                    regions[region]["total"] += 1
                    if req.get("status") in ("completed", "delivered", "satisfied"):
                        regions[region]["fulfilled"] += 1
                    elif req.get("status") == "pending":
                        regions[region]["pending"] += 1

            # Calculate fairness metrics
            fulfillment_rates = []
            region_totals = []
            for region, data in regions.items():
                if data["total"] >= 3:  # Minimum threshold
                    rate = data["fulfilled"] / max(data["total"], 1)
                    fulfillment_rates.append(rate)
                    region_totals.append(data["total"])

            fairness_score = 100
            std_dev = 0.0
            if fulfillment_rates:
                std_dev = statistics.stdev(fulfillment_rates) if len(fulfillment_rates) > 1 else 0
                # Penalize high variance
                fairness_score = max(100 - int(std_dev * 50), 0)

            max_gap = 0.0
            disparity_ratio = 1.0
            if fulfillment_rates:
                max_gap = max(fulfillment_rates) - min(fulfillment_rates)
                min_rate = max(min(fulfillment_rates), 0.0001)
                disparity_ratio = max(fulfillment_rates) / min_rate

            gini_like = self._gini_like(fulfillment_rates)

            # Analyze by resource type priority
            priority_analysis = defaultdict(lambda: {"total": 0, "fulfilled": 0})
            for req in requests:
                priority = self._safe_int(req.get("priority"), 5)
                priority_analysis[priority]["total"] += 1
                if req.get("status") in ("completed", "delivered", "satisfied"):
                    priority_analysis[priority]["fulfilled"] += 1

            high_priority_fulfillment = self._weighted_priority_fulfillment(priority_analysis, priorities={1, 2, 3})
            low_priority_fulfillment = self._weighted_priority_fulfillment(priority_analysis, priorities={7, 8, 9, 10})
            priority_gap = max(0.0, high_priority_fulfillment - low_priority_fulfillment)

            equity_metrics = {
                "regional_rate_std_dev": round(std_dev, 4),
                "regional_max_gap": round(max_gap, 4),
                "regional_disparity_ratio": round(disparity_ratio, 4),
                "regional_gini_like": round(gini_like, 4),
                "high_priority_fulfillment": round(high_priority_fulfillment, 4),
                "low_priority_fulfillment": round(low_priority_fulfillment, 4),
                "priority_gap": round(priority_gap, 4),
            }

            return {
                "fairness_score": fairness_score,
                "fairness_status": "good" if fairness_score >= 80 else "fair" if fairness_score >= 60 else "needs_attention",
                "regional_distribution": {
                    "regions_analyzed": len(regions),
                    "avg_fulfillment_rate": round(sum(fulfillment_rates) / max(len(fulfillment_rates), 1) * 100, 1) if fulfillment_rates else 0,
                    "variance": round(statistics.stdev(fulfillment_rates) * 100, 1) if len(fulfillment_rates) > 1 else 0,
                },
                "equity_metrics": equity_metrics,
                "priority_fairness": {
                    f"priority_{p}": {
                        "total": d["total"],
                        "fulfilled": d["fulfilled"],
                        "rate": round(d["fulfilled"] / max(d["total"], 1) * 100, 1)
                    }
                    for p, d in sorted(priority_analysis.items())
                },
                "recommendations": self._get_fairness_recommendations(
                    fairness_score,
                    regions,
                    priority_analysis,
                    equity_metrics,
                ),
            }

        except Exception as e:
            logger.error(f"Error generating fairness insights: {e}")
            return {"error": str(e)}

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _weighted_priority_fulfillment(self, priority_analysis: dict, priorities: set[int]) -> float:
        total = 0
        fulfilled = 0
        for priority, data in priority_analysis.items():
            p = self._safe_int(priority, 5)
            if p not in priorities:
                continue
            total += data.get("total", 0)
            fulfilled += data.get("fulfilled", 0)
        return (fulfilled / max(total, 1)) if total else 0.0

    def _gini_like(self, values: list[float]) -> float:
        if not values:
            return 0.0
        arr = sorted(max(0.0, float(v)) for v in values)
        n = len(arr)
        if n == 0:
            return 0.0
        total = sum(arr)
        if total <= 0:
            return 0.0
        cumulative = sum((i + 1) * v for i, v in enumerate(arr))
        return (2 * cumulative) / (n * total) - (n + 1) / n

    def _get_fairness_recommendations(
        self,
        fairness_score: int,
        regions: dict,
        priority_analysis: dict,
        equity_metrics: dict[str, float],
    ) -> list[str]:
        """Generate fairness improvement recommendations."""
        recommendations = []

        if fairness_score < 60:
            recommendations.append("Critical: Review resource allocation policies for geographic equity")

        if equity_metrics.get("regional_max_gap", 0.0) > 0.35:
            recommendations.append("Regional fulfillment gap is high; rebalance dispatch capacity toward underserved zones")

        if equity_metrics.get("regional_disparity_ratio", 1.0) > 2.0:
            recommendations.append("Top-performing regions are receiving over 2x fulfillment versus lowest regions; apply zone-level fairness constraints")

        if equity_metrics.get("priority_gap", 0.0) > 0.20:
            recommendations.append("High-priority requests are not being fulfilled fast enough relative to lower priorities; tighten priority SLA enforcement")

        # Check for ignored priorities
        for p, data in priority_analysis.items():
            if data["total"] > 10 and data["fulfilled"] / max(data["total"], 1) < 0.3:
                recommendations.append(f"Warning: Priority {p} requests have low fulfillment rate ({round(data['fulfilled'] / max(data['total'], 1) * 100, 1)}%)")

        # Check for underserved regions
        underserved = [(r, d) for r, d in regions.items() if d["total"] >= 5 and d["fulfilled"] / max(d["total"], 1) < 0.3]
        if len(underserved) > len(regions) * 0.3:
            recommendations.append(f"Warning: {len(underserved)} regions show low fulfillment rates - investigate allocation barriers")

        return recommendations[:5]

    # ─────────────────────────────────────────────────────────────
    # COMPREHENSIVE DASHBOARD DATA
    # ─────────────────────────────────────────────────────────────

    async def get_comprehensive_insights(self) -> dict[str, Any]:
        """
        Get all insights in one comprehensive call for dashboard loading.
        """
        return {
            "victim_submissions": await self.get_victim_submission_insights(),
            "platform_health": await self.get_platform_health_insights(),
            "resource_optimization": await self.get_resource_optimization_insights(),
            "anomalies": await self.get_anomaly_insights(),
            "fairness": await self.get_fairness_insights(),
            "generated_at": datetime.now(UTC).isoformat(),
        }


# Singleton instance
ai_insights_service = AIInsightsService()