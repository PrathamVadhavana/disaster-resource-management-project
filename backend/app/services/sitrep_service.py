"""
Phase 5 - Situation Report Generation Service.

Gathers structured data from Supabase and generates template-based
markdown situation reports - no external AI API needed (free).
"""

import os
import time
import json
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List

import httpx

from app.database import supabase_admin
from app.core.phase5_config import phase5_config

logger = logging.getLogger("sitrep_service")


class SitrepService:
    """Generates template-based situation reports (no paid API required)."""

    def __init__(self):
        self.model = "rule-based"

    # -- Data gathering --

    async def _gather_active_disasters(self) -> List[Dict]:
        try:
            resp = (
                supabase_admin.table("disasters")
                .select("id, type, severity, status, title, description, affected_population, casualties, estimated_damage, start_date, created_at")
                .in_("status", ["active", "monitoring"])
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"Error fetching disasters: {e}")
            return []

    async def _gather_resource_utilization(self) -> Dict:
        try:
            all_resp = supabase_admin.table("resources").select("id, type, status, quantity").execute()
            resources = all_resp.data or []
            total = len(resources)
            by_status = {}
            by_type = {}
            for r in resources:
                status = r.get("status", "unknown")
                rtype = r.get("type", "other")
                by_status[status] = by_status.get(status, 0) + 1
                by_type[rtype] = by_type.get(rtype, 0) + r.get("quantity", 0)
            allocated = by_status.get("allocated", 0) + by_status.get("deployed", 0) + by_status.get("in_transit", 0)
            utilization_pct = round(allocated / total * 100, 1) if total > 0 else 0
            return {"total_resources": total, "utilization_pct": utilization_pct, "by_status": by_status, "by_type": by_type}
        except Exception as e:
            logger.error(f"Error fetching resources: {e}")
            return {"total_resources": 0, "utilization_pct": 0, "by_status": {}, "by_type": {}}

    async def _gather_open_requests(self) -> Dict:
        try:
            resp = (
                supabase_admin.table("resource_requests")
                .select("id, resource_type, priority, status")
                .in_("status", ["pending", "approved", "assigned", "in_progress"])
                .execute()
            )
            requests = resp.data or []
            by_priority = {}; by_type = {}; by_status = {}
            for r in requests:
                p = r.get("priority", "medium"); t = r.get("resource_type", "other"); s = r.get("status", "pending")
                by_priority[p] = by_priority.get(p, 0) + 1
                by_type[t] = by_type.get(t, 0) + 1
                by_status[s] = by_status.get(s, 0) + 1
            return {"total_open": len(requests), "by_priority": by_priority, "by_type": by_type, "by_status": by_status}
        except Exception as e:
            logger.error(f"Error fetching requests: {e}")
            return {"total_open": 0, "by_priority": {}, "by_type": {}, "by_status": {}}

    async def _gather_prediction_summaries(self) -> Dict:
        try:
            since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            resp = (
                supabase_admin.table("predictions")
                .select("id, prediction_type, confidence_score, predicted_severity, created_at")
                .gte("created_at", since)
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
            predictions = resp.data or []
            by_type = {}; avg_confidence = {}
            for p in predictions:
                ptype = p.get("prediction_type", "unknown"); conf = p.get("confidence_score", 0)
                if ptype not in by_type:
                    by_type[ptype] = 0; avg_confidence[ptype] = []
                by_type[ptype] += 1; avg_confidence[ptype].append(conf)
            for k, v in avg_confidence.items():
                avg_confidence[k] = round(sum(v) / len(v), 3) if v else 0
            return {"total_24h": len(predictions), "by_type": by_type, "avg_confidence": avg_confidence}
        except Exception as e:
            logger.error(f"Error fetching predictions: {e}")
            return {"total_24h": 0, "by_type": {}, "avg_confidence": {}}

    async def _gather_recent_ingestion(self) -> Dict:
        try:
            since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            resp = (
                supabase_admin.table("ingested_events")
                .select("id, event_type, severity, processed")
                .gte("ingested_at", since)
                .execute()
            )
            events = resp.data or []
            by_type = {}; by_severity = {}; processed_count = 0
            for e in events:
                etype = e.get("event_type", "unknown"); sev = e.get("severity", "unknown")
                by_type[etype] = by_type.get(etype, 0) + 1
                by_severity[sev] = by_severity.get(sev, 0) + 1
                if e.get("processed"): processed_count += 1
            return {"total_24h": len(events), "processed": processed_count, "by_type": by_type, "by_severity": by_severity}
        except Exception as e:
            logger.error(f"Error fetching ingestion stats: {e}")
            return {"total_24h": 0, "processed": 0, "by_type": {}, "by_severity": {}}

    async def _gather_anomaly_summary(self) -> Dict:
        try:
            resp = (
                supabase_admin.table("anomaly_alerts")
                .select("id, anomaly_type, severity, title, status")
                .eq("status", "active")
                .order("detected_at", desc=True)
                .limit(20)
                .execute()
            )
            alerts = resp.data or []
            return {"active_count": len(alerts), "alerts": [{"type": a["anomaly_type"], "severity": a["severity"], "title": a["title"]} for a in alerts]}
        except Exception as e:
            logger.error(f"Error fetching anomalies: {e}")
            return {"active_count": 0, "alerts": []}

    async def gather_all_data(self) -> Dict[str, Any]:
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
            "report_date": date.today().isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "active_disasters": results[0] if not isinstance(results[0], Exception) else [],
            "resource_utilization": results[1] if not isinstance(results[1], Exception) else {},
            "open_requests": results[2] if not isinstance(results[2], Exception) else {},
            "prediction_summaries": results[3] if not isinstance(results[3], Exception) else {},
            "ingestion_stats": results[4] if not isinstance(results[4], Exception) else {},
            "anomaly_summary": results[5] if not isinstance(results[5], Exception) else {},
        }

    # -- Template-based report generation (free) --

    def _generate_markdown(self, data: Dict[str, Any], report_type: str) -> str:
        disasters = data.get("active_disasters", [])
        resources = data.get("resource_utilization", {})
        requests = data.get("open_requests", {})
        predictions = data.get("prediction_summaries", {})
        ingestion = data.get("ingestion_stats", {})
        anomalies = data.get("anomaly_summary", {})

        lines = []
        lines.append(f"# Situation Report - {data['report_date']}")
        lines.append(f"*{report_type.title()} report generated at {data['generated_at'][:19]} UTC*\n")

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
            parts.append(f". Resource utilization is at **{util_pct}%** with **{total_requests} open victim request(s)**")
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
        lines.append(f"- **Ingested Events (24h):** {ingestion.get('total_24h', 0)} ({ingestion.get('processed', 0)} processed)")
        lines.append(f"- **Active Anomaly Alerts:** {n_anomalies}\n")

        # Active Disasters
        lines.append("## 3. Active Disasters Status\n")
        if disasters:
            for d in disasters[:10]:
                sev = d.get("severity", "unknown").upper()
                lines.append(f"### {d.get('title', 'Untitled')} [{sev}]")
                lines.append(f"- **Type:** {d.get('type', 'unknown')}")
                lines.append(f"- **Status:** {d.get('status', 'unknown')}")
                if d.get("affected_population"): lines.append(f"- **Affected Population:** {d['affected_population']:,}")
                if d.get("casualties"): lines.append(f"- **Casualties:** {d['casualties']:,}")
                if d.get("estimated_damage"): lines.append(f"- **Estimated Damage:** ${d['estimated_damage']:,.0f}")
                if d.get("description"): lines.append(f"- {d['description'][:200]}")
                lines.append("")
        else:
            lines.append("No active disasters.\n")

        # Resource Status
        lines.append("## 4. Resource Status & Gaps\n")
        by_status = resources.get("by_status", {})
        if by_status:
            lines.append("| Status | Count |"); lines.append("|--------|-------|")
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
            lines.append("| Status | Count |"); lines.append("|--------|-------|")
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
                lines.append("| Type | Count | Avg Confidence |"); lines.append("|------|-------|----------------|")
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
                lines.append(f"- **[{alert.get('severity', 'medium').upper()}]** {alert.get('title', 'Unknown')} ({alert.get('type', '')})")
            lines.append("")
        else:
            lines.append("No active anomaly alerts.\n")

        # Recommendations
        lines.append("## 8. Recommendations\n")
        rec_num = 1
        if critical_disasters:
            lines.append(f"{rec_num}. **Prioritize critical-severity disasters** - {len(critical_disasters)} disaster(s) at critical level require immediate coordinator attention.")
            rec_num += 1
        if critical_requests:
            lines.append(f"{rec_num}. **Address critical victim requests** - {critical_requests} request(s) marked critical are awaiting action.")
            rec_num += 1
        if util_pct > 80:
            lines.append(f"{rec_num}. **Replenish resources** - utilization is at {util_pct}%, risking shortages.")
            rec_num += 1
        if n_anomalies:
            lines.append(f"{rec_num}. **Investigate anomaly alerts** - {n_anomalies} active alert(s) may indicate emerging issues.")
            rec_num += 1
        pending_count = by_req_status.get("pending", 0) if by_req_status else 0
        if pending_count > 10:
            lines.append(f"{rec_num}. **Clear request backlog** - {pending_count} requests still in pending status.")
            rec_num += 1
        if rec_num == 1:
            lines.append("No urgent recommendations at this time. Continue monitoring.")
        lines.append("")
        lines.append("---")
        lines.append(f"*Report generated by Rule-Based SitRep Engine - {data['generated_at'][:19]} UTC*")
        return "\n".join(lines)

    # -- Report generation --

    async def generate_report(self, report_type: str = "daily", generated_by: str = "system") -> Dict[str, Any]:
        start_ms = time.time()
        data = await self.gather_all_data()
        try:
            markdown_body = self._generate_markdown(data, report_type)
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
                    in_exec = True; continue
                if in_exec and line.strip() and not line.startswith("#"):
                    summary = line.strip(); break
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
            db_resp = supabase_admin.table("situation_reports").insert(record).execute()
            stored = db_resp.data[0] if db_resp.data else record
            if phase5_config.SITREP_EMAIL_ENABLED and phase5_config.SITREP_ADMIN_EMAILS:
                await self._email_report(stored, phase5_config.SITREP_ADMIN_EMAILS)
            logger.info(f"Situation report generated in {generation_time}ms: {title}")
            return stored
        except Exception as e:
            generation_time = int((time.time() - start_ms) * 1000)
            logger.error(f"Failed to generate situation report: {e}")
            error_record = {
                "report_date": data["report_date"], "report_type": report_type,
                "title": f"FAILED: Situation Report - {data['report_date']}",
                "markdown_body": "", "model_used": self.model, "generated_by": generated_by,
                "generation_time_ms": generation_time, "status": "failed", "error_message": str(e),
            }
            try: supabase_admin.table("situation_reports").insert(error_record).execute()
            except Exception: pass
            raise

    async def _email_report(self, report: Dict, recipients: List[str]) -> None:
        if not phase5_config.SENDGRID_API_KEY:
            logger.warning("SendGrid not configured, skipping email")
            return
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for email in recipients:
                    await client.post(
                        "https://api.sendgrid.com/v3/mail/send",
                        headers={"Authorization": f"Bearer {phase5_config.SENDGRID_API_KEY}", "Content-Type": "application/json"},
                        json={
                            "personalizations": [{"to": [{"email": email}]}],
                            "from": {"email": phase5_config.SENDGRID_FROM_EMAIL},
                            "subject": report.get("title", "Situation Report"),
                            "content": [{"type": "text/plain", "value": report.get("markdown_body", "")}],
                        },
                    )
            supabase_admin.table("situation_reports").update({"emailed_to": recipients, "status": "emailed"}).eq("id", report["id"]).execute()
        except Exception as e:
            logger.error(f"Failed to email report: {e}")

    # -- List & get reports --

    async def list_reports(self, report_type: Optional[str] = None, limit: int = 20, offset: int = 0) -> List[Dict]:
        query = (
            supabase_admin.table("situation_reports")
            .select("id, report_date, report_type, title, summary, key_metrics, status, generation_time_ms, created_at")
            .order("report_date", desc=True)
            .range(offset, offset + limit - 1)
        )
        if report_type: query = query.eq("report_type", report_type)
        resp = query.execute()
        return resp.data or []

    async def get_report(self, report_id: str) -> Optional[Dict]:
        resp = supabase_admin.table("situation_reports").select("*").eq("id", report_id).single().execute()
        return resp.data

    async def get_latest_report(self) -> Optional[Dict]:
        resp = (
            supabase_admin.table("situation_reports").select("*")
            .eq("status", "generated").order("created_at", desc=True).limit(1).execute()
        )
        return resp.data[0] if resp.data else None
