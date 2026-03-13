"""
Privacy Protection Service

This service ensures data privacy and protection across the platform:
- PII (Personally Identifiable Information) detection and masking
- Data anonymization for analytics
- Consent management
- Data retention policies
- Privacy compliance helpers
- GDPR/privacy-aware data access
"""

import hashlib
import logging
import re
import traceback
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class PrivacyService:
    """
    Service for protecting privacy while enabling analytics.
    """

    # PII patterns for detection
    PII_PATTERNS = {
        "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
    }

    # Sensitive fields that should be masked in analytics
    SENSITIVE_FIELDS = {
        "users": ["password", "email", "phone", "full_name", "avatar_url"],
        "victim_details": ["phone", "email", "full_name", "personal_details"],
        "resource_requests": [],  # Generally OK for analytics
    }

    def __init__(self):
        self.hash_salt = "privacy_salt_2024"  # Should be from config

    # ─────────────────────────────────────────────────────────────
    # PII DETECTION & MASKING
    # ─────────────────────────────────────────────────────────────

    def detect_pii(self, text: str) -> list[dict]:
        """
        Detect PII patterns in text.
        Returns list of detected PII types and locations.
        """
        if not text:
            return []

        findings = []
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                findings.append({
                    "type": pii_type,
                    "value": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                })

        return findings

    def mask_pii(self, text: str, mask_char: str = "*") -> str:
        """
        Mask detected PII in text.
        """
        if not text:
            return text

        result = text
        for pii_type, pattern in self.PII_PATTERNS.items():
            result = re.sub(pattern, self._get_mask(pii_type, mask_char), result)

        return result

    def _get_mask(self, pii_type: str, mask_char: str) -> str:
        """Get appropriate mask for PII type."""
        masks = {
            "email": f"{mask_char}***{mask_char}@{mask_char}***.com",
            "phone": f"{mask_char}{mask_char}{mask_char}-{mask_char}{mask_char}{mask_char}-{mask_char}{mask_char}{mask_char}{mask_char}",
            "ssn": f"{mask_char}{mask_char}{mask_char}-{mask_char}{mask_char}-{mask_char}{mask_char}{mask_char}{mask_char}",
            "credit_card": f"{mask_char}{mask_char}{mask_char}{mask_char}-{mask_char}{mask_char}{mask_char}{mask_char}-****-****",
        }
        return masks.get(pii_type, mask_char * 10)

    # ─────────────────────────────────────────────────────────────
    # DATA ANONYMIZATION
    # ─────────────────────────────────────────────────────────────

    def anonymize_user_data(self, user_data: dict, level: str = "standard") -> dict:
        """
        Anonymize user data for analytics.
        
        Levels:
        - "minimal": Only remove direct identifiers
        - "standard": Remove identifiers + pseudonymous IDs
        - "strict": Full anonymization with k-anonymity
        """
        if not user_data:
            return {}

        anonymized = dict(user_data)

        if level in ("standard", "strict"):
            # Replace user ID with hash
            if "id" in anonymized:
                anonymized["id"] = self._hash_identifier(anonymized["id"])

        # Remove direct identifiers
        direct_identifiers = ["email", "phone", "full_name", "avatar_url", "password"]
        for field in direct_identifiers:
            if field in anonymized:
                anonymized[field] = "[REDACTED]"

        if level == "strict":
            # Apply additional anonymization
            anonymized = self._apply_k_anonymity(anonymized)

        return anonymized

    def _hash_identifier(self, identifier: str) -> str:
        """Create a consistent hash for identifiers."""
        combined = f"{self.hash_salt}_{identifier}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _apply_k_anonymity(self, data: dict) -> dict:
        """Apply k-anonymity by generalizing quasi-identifiers."""
        # Generalize location to region level
        if "location_lat" in data and "location_long" in data:
            lat = data.get("location_lat")
            lng = data.get("location_long")
            if lat is not None and lng is not None:
                # Round to ~10km precision (approx 0.1 degrees)
                data["location_region"] = f"{round(lat, 1)}_{round(lng, 1)}"
                del data["location_lat"]
                del data["location_long"]

        # Generalize timestamps to dates
        if "created_at" in data:
            created = data.get("created_at")
            if isinstance(created, str) and len(created) > 10:
                data["created_date"] = created[:10]
                del data["created_at"]

        return data

    def anonymize_batch(self, records: list[dict], id_field: str = "user_id") -> list[dict]:
        """
        Anonymize a batch of records while maintaining consistency.
        """
        id_hashes = {}  # Cache to maintain consistency

        anonymized = []
        for record in records:
            anon = dict(record)

            # Anonymize ID field
            if id_field in anon:
                orig_id = anon[id_field]
                if orig_id not in id_hashes:
                    id_hashes[orig_id] = self._hash_identifier(orig_id)
                anon[id_field] = id_hashes[orig_id]

            # Remove other direct identifiers
            for field in ["email", "phone", "full_name"]:
                if field in anon:
                    anon[field] = "[REDACTED]"

            anonymized.append(anon)

        return anonymized

    # ─────────────────────────────────────────────────────────────
    # PRIVACY-PRESERVING AGGREGATION
    # ─────────────────────────────────────────────────────────────

    def aggregate_privacy_preserving(
        self,
        records: list[dict],
        group_by: str,
        aggregates: list[str],
        min_group_size: int = 5
    ) -> list[dict]:
        """
        Perform aggregation while ensuring k-anonymity.
        Only returns groups with minimum size to prevent re-identification.
        """
        from collections import defaultdict

        groups = defaultdict(list)
        for record in records:
            key = record.get(group_by)
            if key:
                groups[key].append(record)

        results = []
        for group_key, group_records in groups.items():
            # Skip small groups
            if len(group_records) < min_group_size:
                continue

            result = {group_by: group_key, "count": len(group_records)}

            # Calculate aggregates
            for agg_field in aggregates:
                values = [r.get(agg_field) for r in group_records if r.get(agg_field) is not None]
                if values:
                    try:
                        numeric_values = [float(v) for v in values]
                        result[f"{agg_field}_avg"] = round(sum(numeric_values) / len(numeric_values), 2)
                        result[f"{agg_field}_sum"] = round(sum(numeric_values), 2)
                    except (ValueError, TypeError):
                        # For non-numeric, just count
                        result[f"{agg_field}_count"] = len(values)

            results.append(result)

        return sorted(results, key=lambda x: x.get("count", 0), reverse=True)

    # ─────────────────────────────────────────────────────────────
    # PRIVACY AUDIT HELPERS
    # ─────────────────────────────────────────────────────────────

    def audit_data_exposure(self, record: dict) -> dict[str, Any]:
        """
        Audit a record for potential privacy exposure.
        Returns risk assessment and recommendations.
        """
        risks = []
        recommendations = []

        # Check for PII in text fields
        text_fields = ["description", "notes", "field_notes", "admin_note"]
        for field in text_fields:
            if field in record and record[field]:
                pii_found = self.detect_pii(str(record[field]))
                if pii_found:
                    risks.append({
                        "field": field,
                        "pii_types": [p["type"] for p in pii_found],
                        "severity": "high" if any(p["type"] in ["ssn", "credit_card"] for p in pii_found) else "medium",
                    })
                    recommendations.append(f"Review and mask PII in {field}")

        # Check for exposed identifiers
        identifier_fields = ["email", "phone", "full_name"]
        exposed_ids = [f for f in identifier_fields if f in record and record[f] and record[f] != "[REDACTED]"]
        if exposed_ids:
            risks.append({
                "type": "exposed_identifiers",
                "fields": exposed_ids,
                "severity": "high",
            })
            recommendations.append("Anonymize or redact direct identifiers")

        return {
            "risks_found": len(risks),
            "risks": risks,
            "recommendations": recommendations,
            "overall_risk": "high" if any(r.get("severity") == "high" for r in risks) else "medium" if risks else "low",
        }

    def check_compliance(self, data_handling: dict) -> dict[str, Any]:
        """
        Check privacy compliance for data handling operations.
        """
        issues = []
        warnings = []

        # Check for proper consent
        if data_handling.get("requires_consent") and not data_handling.get("consent_verified"):
            issues.append("Data processing without verified consent")

        # Check for proper anonymization
        if data_handling.get("includes_pii") and not data_handling.get("anonymized"):
            warnings.append("Processing PII without anonymization - ensure explicit consent")

        # Check retention policy
        retention_days = data_handling.get("retention_days", 0)
        if retention_days > 365:
            warnings.append(f"Long retention period ({retention_days} days) - verify necessity")

        # Check for proper access controls
        if data_handling.get("sensitive_data") and not data_handling.get("access_restricted"):
            issues.append("Sensitive data without restricted access")

        return {
            "compliant": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "compliance_score": max(100 - len(issues) * 20 - len(warnings) * 5, 0),
        }

    # ─────────────────────────────────────────────────────────────
    # DATA RETENTION MANAGEMENT
    # ─────────────────────────────────────────────────────────────

    def get_data_retention_info(self) -> dict[str, Any]:
        """
        Get data retention policies and recommendations.
        """
        return {
            "policies": {
                "active_records": "Indefinite (until resolved)",
                "pending_requests": "2 years after resolution",
                "audit_logs": "3 years",
                "user_sessions": "90 days",
                "analytics_data": "1 year (anonymized)",
            },
            "recommendations": [
                "Implement automated cleanup for resolved disasters > 1 year old",
                "Archive completed requests > 2 years",
                "Rotate analytics data to anonymized archive quarterly",
                "Review and purge inactive user accounts annually",
            ],
            "compliance_notes": [
                "GDPR: Right to erasure applies - implement deletion pipeline",
                "Retain audit logs for legal requirements",
                "Keep aggregated metrics for trend analysis (already anonymized)",
            ],
        }

    # ─────────────────────────────────────────────────────────────
    # EXPORT WITH PRIVACY
    # ─────────────────────────────────────────────────────────────

    def prepare_analytics_export(self, records: list[dict], include_pii: bool = False) -> list[dict]:
        """
        Prepare records for analytics export with appropriate privacy controls.
        """
        exported = []

        for record in records:
            # Start with anonymized data
            anon_record = self.anonymize_user_data(record, level="standard")

            # Optionally include PII (should only be true for authorized admins)
            if include_pii:
                # For authorized export, use minimal masking
                for field in ["email", "phone"]:
                    if field in record:
                        # Partial masking
                        value = str(record.get(field, ""))
                        if "@" in value:
                            parts = value.split("@")
                            anon_record[field] = f"{parts[0][:2]}***@{parts[1]}"
                        elif len(value) >= 4:
                            anon_record[field] = f"***-***-{value[-4:]}"
                        else:
                            anon_record[field] = "***"
            else:
                # Ensure no PII
                for field in ["email", "phone", "full_name"]:
                    if field in anon_record:
                        anon_record[field] = "[REDACTED]"

            exported.append(anon_record)

        return exported


# Singleton instance
privacy_service = PrivacyService()