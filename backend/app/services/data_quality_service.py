"""
Data Validation and Quality Assurance Service

This service ensures data integrity and quality across the platform:
- Input validation for victim submissions
- Data completeness checks
- Anomaly detection in submitted data
- Duplicate detection
- Data consistency validation
- Quality scoring and reporting
"""

import logging
import re
import traceback
from datetime import UTC, datetime, timedelta
from typing import Any
from collections import defaultdict

from app.database import db_admin

logger = logging.getLogger(__name__)


class DataQualityService:
    """
    Service for validating and ensuring data quality across the platform.
    """

    def __init__(self):
        self.quality_thresholds = {
            "min_completeness": 0.7,  # 70% fields must be filled
            "max_duplicate_ratio": 0.05,  # Max 5% duplicates
            "min_valid_coords": 0.9,  # 90% of locations must be valid
        }

    # ─────────────────────────────────────────────────────────────
    # VICTIM SUBMISSION VALIDATION
    # ─────────────────────────────────────────────────────────────

    async def validate_victim_submission(self, submission: dict) -> dict[str, Any]:
        """
        Validate a victim resource request submission for quality.
        Returns validation result with issues and quality score.
        """
        issues = []
        warnings = []

        # Check required fields
        required_fields = ["resource_type", "quantity", "priority"]
        for field in required_fields:
            if not submission.get(field):
                issues.append(f"Missing required field: {field}")

        # Validate resource type
        valid_types = ["food", "water", "medical", "shelter", "personnel", "equipment", "other"]
        if submission.get("resource_type") and submission["resource_type"] not in valid_types:
            issues.append(f"Invalid resource type: {submission['resource_type']}")

        # Validate priority range
        priority = submission.get("priority")
        if priority is not None:
            if not isinstance(priority, int) or priority < 1 or priority > 10:
                issues.append("Priority must be an integer between 1 and 10")

        # Validate quantity
        quantity = submission.get("quantity")
        if quantity is not None:
            if not isinstance(quantity, (int, float)) or quantity <= 0:
                issues.append("Quantity must be a positive number")

        # Validate coordinates if provided
        lat = submission.get("latitude")
        lng = submission.get("longitude")
        if lat is not None and lng is not None:
            if not (-90 <= lat <= 90):
                issues.append("Latitude must be between -90 and 90")
            if not (-180 <= lng <= 180):
                issues.append("Longitude must be between -180 and 180")

        # Check for suspicious patterns (basic spam detection)
        if submission.get("description"):
            if self._is_suspicious_description(submission["description"]):
                warnings.append("Description contains suspicious patterns")

        # Calculate quality score
        completeness = self._calculate_completeness(submission)
        quality_score = self._calculate_quality_score(issues, warnings, completeness)

        return {
            "valid": len(issues) == 0,
            "quality_score": quality_score,
            "issues": issues,
            "warnings": warnings,
            "completeness": completeness,
            "recommendations": self._get_recommendations(issues, warnings),
        }

    def _is_suspicious_description(self, description: str) -> bool:
        """Basic detection of suspicious/spam content."""
        if not description:
            return False

        # Check for excessive repetition
        words = description.lower().split()
        if len(words) > 5:
            word_counts = defaultdict(int)
            for word in words:
                word_counts[word] += 1
            max_repeat = max(word_counts.values()) / max(len(words), 1)
            if max_repeat > 0.5:
                return True

        # Check for excessive caps
        caps_ratio = sum(1 for c in description if c.isupper()) / max(len(description), 1)
        if caps_ratio > 0.7 and len(description) > 20:
            return True

        # Check for suspicious keywords (basic)
        suspicious = ["buy", "sell", "cheap", "free money", "winner", "click here"]
        if any(s in description.lower() for s in suspicious):
            return True

        return False

    def _calculate_completeness(self, submission: dict) -> float:
        """Calculate how complete the submission is."""
        # Key fields for victim requests
        important_fields = [
            "resource_type", "quantity", "priority", "description",
            "latitude", "longitude", "address", "items"
        ]

        filled = sum(1 for f in important_fields if submission.get(f))
        return filled / len(important_fields)

    def _calculate_quality_score(self, issues: list, warnings: list, completeness: float) -> int:
        """Calculate overall quality score (0-100)."""
        score = 100
        score -= len(issues) * 15  # Major issues
        score -= len(warnings) * 5  # Minor warnings
        score -= (1 - completeness) * 30  # Completeness penalty
        return max(score, 0)

    def _get_recommendations(self, issues: list, warnings: list) -> list[str]:
        """Get actionable recommendations based on validation results."""
        recs = []

        if any("missing" in i.lower() for i in issues):
            recs.append("Please fill in all required fields before submitting")

        if any("priority" in i.lower() for i in issues):
            recs.append("Set an appropriate priority level (1=highest, 10=lowest)")

        if any("coordinates" in i.lower() for i in issues):
            recs.append("Please provide accurate location coordinates")

        if any("suspicious" in w.lower() for w in warnings):
            recs.append("Please ensure your description is factual and clear")

        return recs[:3]

    # ─────────────────────────────────────────────────────────────
    # BATCH DATA QUALITY ASSESSMENT
    # ─────────────────────────────────────────────────────────────

    async def assess_batch_quality(self, table: str, days: int = 7) -> dict[str, Any]:
        """
        Assess overall data quality for a table over a time period.
        """
        try:
            since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

            if table == "resource_requests":
                return await self._assess_request_quality(since)
            elif table == "victim_details":
                return await self._assess_victim_quality(since)
            elif table == "disasters":
                return await self._assess_disaster_quality(since)
            else:
                return {"error": f"Unknown table: {table}"}

        except Exception as e:
            logger.error(f"Error assessing batch quality: {e}")
            traceback.print_exc()
            return {"error": str(e)}

    async def _assess_request_quality(self, since: str) -> dict:
        """Assess quality of resource requests."""
        resp = (
            await db_admin.table("resource_requests")
            .select("""
                id, resource_type, quantity, priority, status,
                latitude, longitude, description, created_at
            """)
            .gte("created_at", since)
            .limit(2000)
            .async_execute()
        )
        requests = resp.data or []

        if not requests:
            return {"message": "No recent requests to assess"}

        quality_scores = []
        completeness_scores = []
        issues_summary = defaultdict(int)

        for req in requests:
            result = await self.validate_victim_submission(req)
            quality_scores.append(result["quality_score"])
            completeness_scores.append(result["completeness"])
            for issue in result["issues"]:
                issues_summary[issue] += 1

        import statistics
        return {
            "total_ assessed": len(requests),
            "avg_quality_score": round(statistics.mean(quality_scores), 1),
            "quality_distribution": self._get_distribution(quality_scores),
            "avg_completeness": round(statistics.mean(completeness_scores), 2),
            "common_issues": dict(sorted(issues_summary.items(), key=lambda x: x[1], reverse=True)[:5]),
            "recommendations": self._get_quality_recommendations(quality_scores),
        }

    async def _assess_victim_quality(self, since: str) -> dict:
        """Assess quality of victim profiles."""
        resp = (
            await db_admin.table("victim_details")
            .select("*")
            .gte("updated_at", since)
            .limit(2000)
            .async_execute()
        )
        profiles = resp.data or []

        if not profiles:
            return {"message": "No recent profiles to assess"}

        # Check key fields
        completeness = {
            "location": sum(1 for p in profiles if p.get("location_lat") and p.get("location_long")),
            "needs": sum(1 for p in profiles if p.get("needs")),
            "status": sum(1 for p in profiles if p.get("current_status")),
            "medical": sum(1 for p in profiles if p.get("medical_needs")),
        }

        total = len(profiles)
        return {
            "total_profiles": total,
            "completeness": {k: round(v / max(total, 1) * 100, 1) for k, v in completeness.items()},
            "overall_completeness": round(sum(completeness.values()) / (len(completeness) * max(total, 1)) * 100, 1),
        }

    async def _assess_disaster_quality(self, since: str) -> dict:
        """Assess quality of disaster data."""
        resp = (
            await db_admin.table("disasters")
            .select("*")
            .gte("created_at", since)
            .limit(500)
            .async_execute()
        )
        disasters = resp.data or []

        if not disasters:
            return {"message": "No recent disasters to assess"}

        # Check data completeness
        completeness = {
            "location": sum(1 for d in disasters if d.get("location_id")),
            "severity": sum(1 for d in disasters if d.get("severity")),
            "type": sum(1 for d in disasters if d.get("type")),
            "population": sum(1 for d in disasters if d.get("affected_population")),
        }

        total = len(disasters)
        return {
            "total_disasters": total,
            "completeness": {k: round(v / max(total, 1) * 100, 1) for k, v in completeness.items()},
            "severity_distribution": self._get_field_distribution(disasters, "severity"),
            "type_distribution": self._get_field_distribution(disasters, "type"),
        }

    def _get_distribution(self, values: list) -> dict:
        """Get distribution of values."""
        if not values:
            return {}

        import statistics
        return {
            "min": min(values),
            "max": max(values),
            "avg": round(statistics.mean(values), 1),
            "median": round(statistics.median(values), 1),
        }

    def _get_field_distribution(self, items: list[dict], field: str) -> dict:
        """Get distribution of a specific field."""
        counts = defaultdict(int)
        for item in items:
            val = item.get(field, "unknown")
            counts[val] += 1
        return dict(counts)

    def _get_quality_recommendations(self, scores: list) -> list[str]:
        """Get recommendations based on quality scores."""
        import statistics
        avg = statistics.mean(scores)

        if avg < 50:
            return [
                "Critical: Data quality is very low - review submission guidelines",
                "Consider implementing mandatory field validation",
            ]
        elif avg < 70:
            return [
                "Warning: Data quality below threshold - improve validation",
                "Add more field requirements and help text",
            ]
        elif avg < 85:
            return [
                "Good: Data quality is acceptable - continue monitoring",
                "Consider adding optional enhancement fields",
            ]
        else:
            return [
                "Excellent: Data quality is high",
                "Maintain current validation standards",
            ]

    # ─────────────────────────────────────────────────────────────
    # DUPLICATE DETECTION
    # ─────────────────────────────────────────────────────────────

    async def detect_duplicates(self, table: str, days: int = 7) -> dict[str, Any]:
        """
        Detect potential duplicate entries in a table.
        """
        try:
            since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

            if table == "resource_requests":
                return await self._detect_request_duplicates(since)
            else:
                return {"error": f"Duplicate detection not implemented for {table}"}

        except Exception as e:
            logger.error(f"Error detecting duplicates: {e}")
            return {"error": str(e)}

    async def _detect_request_duplicates(self, since: str) -> dict:
        """Detect duplicate resource requests from same user/location."""
        resp = (
            await db_admin.table("resource_requests")
            .select("id, user_id, resource_type, latitude, longitude, created_at, status")
            .gte("created_at", since)
            .limit(2000)
            .async_execute()
        )
        requests = resp.data or []

        # Find potential duplicates by user + resource type + similar location
        potential_dupes = []
        for i, req1 in enumerate(requests):
            for req2 in requests[i+1:]:
                # Check same user
                if req1.get("user_id") == req2.get("user_id"):
                    # Check same resource type
                    if req1.get("resource_type") == req2.get("resource_type"):
                        # Check within 24 hours
                        try:
                            dt1 = datetime.fromisoformat(req1.get("created_at", "").replace("+00:00", "Z"))
                            dt2 = datetime.fromisoformat(req2.get("created_at", "").replace("+00:00", "Z"))
                            hours_diff = abs((dt1 - dt2).total_seconds() / 3600)
                            if hours_diff < 24:
                                potential_dupes.append({
                                    "request_1": req1.get("id"),
                                    "request_2": req2.get("id"),
                                    "hours_apart": round(hours_diff, 1),
                                    "resource_type": req1.get("resource_type"),
                                })
                        except:
                            pass

        return {
            "total_checked": len(requests),
            "potential_duplicates": len(potential_dupes),
            "duplicate_rate": round(len(potential_dupes) / max(len(requests), 1) * 100, 2),
            "samples": potential_dupes[:10],
        }

    # ─────────────────────────────────────────────────────────────
    # DATA CONSISTENCY CHECKS
    # ─────────────────────────────────────────────────────────────

    async def check_consistency(self) -> dict[str, Any]:
        """
        Check data consistency across related tables.
        """
        try:
            inconsistencies = []

            # Check: orphaned requests (non-existent disaster)
            # Note: This would require checking foreign keys which we can't do directly
            # Instead, check for obvious data inconsistencies

            # Check: inconsistent status values
            status_resp = (
                await db_admin.table("resource_requests")
                .select("status")
                .limit(5000)
                .async_execute()
            )
            statuses = status_resp.data or []
            valid_statuses = {"pending", "in_progress", "completed", "delivered", "satisfied", "rejected", "cancelled"}

            invalid_statuses = [s for s in statuses if s.get("status") not in valid_statuses]
            if invalid_statuses:
                inconsistencies.append({
                    "type": "invalid_status_values",
                    "count": len(invalid_statuses),
                })

            # Check: impossible coordinates
            coord_resp = (
                await db_admin.table("resource_requests")
                .select("id, latitude, longitude")
                .limit(5000)
                .async_execute()
            )
            coords = coord_resp.data or []

            invalid_coords = [c for c in coords if c.get("latitude") and (c["latitude"] < -90 or c["latitude"] > 90)]
            if invalid_coords:
                inconsistencies.append({
                    "type": "invalid_coordinates",
                    "count": len(invalid_coords),
                })

            return {
                "checked_at": datetime.now(UTC).isoformat(),
                "inconsistencies_found": len(inconsistencies),
                "inconsistencies": inconsistencies,
                "overall_health": "good" if len(inconsistencies) == 0 else "needs_attention",
            }

        except Exception as e:
            logger.error(f"Error checking consistency: {e}")
            return {"error": str(e)}


# Singleton instance
data_quality_service = DataQualityService()