"""
Causal Audit Report Generator — PDF report for post-disaster causal analysis.

When a disaster's status changes to ``resolved``, this module produces a
PDF report containing:

1. **Root causes** ranked by causal effect size (ATE)
2. **Top 3 counterfactual interventions** that would have reduced
   casualties the most
3. **Causal graph** summary and estimation metadata

The PDF is uploaded to Supabase Storage (or saved locally as fallback)
and a reference is stored in the database.
"""

from __future__ import annotations

import io
import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("audit_report_generator")


class CausalAuditReportGenerator:
    """Generates a Causal Audit Report PDF for a resolved disaster."""

    async def generate(self, disaster: dict) -> str:
        """Build the PDF, upload it, and return the download URL.

        Parameters
        ----------
        disaster : dict
            Full disaster document from the database.

        Returns
        -------
        str
            Public URL (or database record path) of the uploaded report.
        """
        from ml.causal_model import DisasterCausalModel

        disaster_id = disaster.get("id", "unknown")
        logger.info("Generating causal audit report for disaster %s", disaster_id)

        # --- 1. Initialise causal model ---
        cm = DisasterCausalModel()

        # --- 2. Build observation from disaster record ---
        observation = self._disaster_to_observation(disaster)

        # --- 3. Rank root causes ---
        root_causes_casualties = cm.rank_root_causes("casualties")
        root_causes_damage = cm.rank_root_causes("economic_damage_usd")

        # --- 4. Top counterfactual interventions ---
        top_interventions = cm.top_counterfactual_interventions(
            observation,
            outcome_var="casualties",
            k=3,
        )

        # --- 5. Render PDF ---
        pdf_bytes = self._render_pdf(
            disaster=disaster,
            observation=observation,
            root_causes_casualties=root_causes_casualties,
            root_causes_damage=root_causes_damage,
            top_interventions=top_interventions,
        )

        # --- 6. Upload ---
        report_url = await self._upload_pdf(disaster_id, pdf_bytes)

        # --- 7. Store reference in database ---
        await self._store_report_ref(disaster_id, report_url)

        logger.info("Audit report for disaster %s uploaded: %s", disaster_id, report_url)
        return report_url

    # ------------------------------------------------------------------
    # Observation mapping (mirrors causal router helper)
    # ------------------------------------------------------------------

    @staticmethod
    def _disaster_to_observation(disaster: dict) -> dict[str, float]:
        return {
            "weather_severity": float(disaster.get("weather_severity", 5.0)),
            "disaster_type": float(disaster.get("disaster_type_code", 5.0)),
            "response_time_hours": float(disaster.get("response_time_hours", 12.0)),
            "resource_availability": float(disaster.get("resource_availability", 3.0)),
            "ngo_proximity_km": float(disaster.get("ngo_proximity_km", 50.0)),
            "resource_quality_score": float(disaster.get("resource_quality_score", 5.0)),
            "casualties": float(disaster.get("casualties", 0)),
            "economic_damage_usd": float(disaster.get("economic_damage_usd", 0)),
        }

    # ------------------------------------------------------------------
    # PDF rendering (reportlab)
    # ------------------------------------------------------------------

    def _render_pdf(
        self,
        disaster: dict,
        observation: dict[str, float],
        root_causes_casualties: list,
        root_causes_damage: list,
        top_interventions: list[dict[str, Any]],
    ) -> bytes:
        """Render the audit report as a PDF and return raw bytes."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontSize=20,
            spaceAfter=12,
            textColor=colors.HexColor("#1a237e"),
        )
        heading_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontSize=14,
            spaceBefore=16,
            spaceAfter=8,
            textColor=colors.HexColor("#283593"),
        )
        body_style = styles["BodyText"]
        small_style = ParagraphStyle(
            "SmallText",
            parent=styles["BodyText"],
            fontSize=8,
            textColor=colors.grey,
        )

        story: list[Any] = []

        # Title
        disaster_id = disaster.get("id", "N/A")
        disaster_name = disaster.get("name", disaster.get("title", "Unknown Disaster"))
        story.append(Paragraph("Causal Audit Report", title_style))
        story.append(
            Paragraph(
                f"<b>Disaster:</b> {disaster_name} &nbsp;|&nbsp; "
                f"<b>ID:</b> {disaster_id} &nbsp;|&nbsp; "
                f"<b>Generated:</b> {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
                body_style,
            )
        )
        story.append(Spacer(1, 12))

        # --- Section 1: Disaster Summary ---
        story.append(Paragraph("1. Disaster Summary", heading_style))
        summary_data = [
            ["Variable", "Value"],
            ["Weather Severity", f"{observation['weather_severity']:.1f}"],
            ["Disaster Type Code", f"{observation['disaster_type']:.1f}"],
            ["Response Time (hrs)", f"{observation['response_time_hours']:.1f}"],
            ["Resource Availability", f"{observation['resource_availability']:.2f}"],
            ["NGO Proximity (km)", f"{observation['ngo_proximity_km']:.1f}"],
            ["Resource Quality Score", f"{observation['resource_quality_score']:.1f}"],
            ["Casualties", f"{observation['casualties']:.0f}"],
            ["Economic Damage (USD)", f"${observation['economic_damage_usd']:,.0f}"],
        ]
        t = Table(summary_data, colWidths=[200, 200])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 16))

        # --- Section 2: Root Causes (Casualties) ---
        story.append(Paragraph("2. Root Causes — Casualties (ranked by effect size)", heading_style))
        story.append(
            Paragraph(
                "Each row shows the Average Treatment Effect (ATE) of a causal factor on casualties. "
                "A positive ATE means increasing that factor increases casualties.",
                body_style,
            )
        )
        story.append(Spacer(1, 6))

        rc_data = [["Rank", "Causal Factor", "ATE", "95% CI", "Refutation"]]
        for i, rc in enumerate(root_causes_casualties, 1):
            ci_str = f"[{rc.confidence_interval[0]:.2f}, {rc.confidence_interval[1]:.2f}]"
            ref_str = "✓ Passed" if rc.refutation_passed else ("✗ Failed" if rc.refutation_passed is False else "—")
            rc_data.append(
                [
                    str(i),
                    rc.treatment.replace("_", " ").title(),
                    f"{rc.ate:.4f}",
                    ci_str,
                    ref_str,
                ]
            )

        t2 = Table(rc_data, colWidths=[40, 160, 80, 120, 80])
        t2.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                    ("ALIGN", (2, 0), (4, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(t2)
        story.append(Spacer(1, 16))

        # --- Section 3: Root Causes (Economic Damage) ---
        story.append(Paragraph("3. Root Causes — Economic Damage (ranked by effect size)", heading_style))

        rc_dmg_data = [["Rank", "Causal Factor", "ATE (USD)", "95% CI"]]
        for i, rc in enumerate(root_causes_damage, 1):
            ci_str = f"[${rc.confidence_interval[0]:,.0f}, ${rc.confidence_interval[1]:,.0f}]"
            rc_dmg_data.append(
                [
                    str(i),
                    rc.treatment.replace("_", " ").title(),
                    f"${rc.ate:,.2f}",
                    ci_str,
                ]
            )

        t3 = Table(rc_dmg_data, colWidths=[40, 160, 120, 160])
        t3.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                    ("ALIGN", (2, 0), (3, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(t3)
        story.append(Spacer(1, 16))

        # --- Section 4: Top 3 Counterfactual Interventions ---
        story.append(
            Paragraph(
                "4. Top Counterfactual Interventions (Casualty Reduction)",
                heading_style,
            )
        )
        story.append(
            Paragraph(
                "These are the single-variable interventions that would have reduced "
                "casualties the most, based on causal effect estimation.",
                body_style,
            )
        )
        story.append(Spacer(1, 6))

        for i, intv in enumerate(top_interventions, 1):
            story.append(
                Paragraph(
                    f"<b>#{i}: {intv['variable'].replace('_', ' ').title()}</b>",
                    body_style,
                )
            )
            intv_data = [
                ["Current Value", "Proposed Value", "Est. Casualties Reduced"],
                [
                    str(intv["current_value"]),
                    str(intv["proposed_value"]),
                    str(intv["estimated_reduction"]),
                ],
            ]
            ti = Table(intv_data, colWidths=[140, 140, 160])
            ti.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4caf50")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTSIZE", (0, 1), (-1, -1), 9),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(ti)
            story.append(
                Paragraph(
                    f"<i>{intv['explanation']}</i>",
                    ParagraphStyle("Explanation", parent=body_style, fontSize=8, textColor=colors.HexColor("#555555")),
                )
            )
            story.append(Spacer(1, 8))

        # --- Footer ---
        story.append(Spacer(1, 24))
        story.append(
            Paragraph(
                "This report was auto-generated by the Causal AI Audit Module using DoWhy "
                "backdoor adjustment. Estimates are based on observational data and domain-encoded "
                "causal assumptions. Confidence intervals are bootstrap-derived (200 replications).",
                small_style,
            )
        )

        doc.build(story)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Upload to Supabase Storage (fallback: local file)
    # ------------------------------------------------------------------

    async def _upload_pdf(self, disaster_id: str, pdf_bytes: bytes) -> str:
        """Upload PDF to Supabase Storage or save locally."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"causal_audit_{disaster_id}_{timestamp}.pdf"

        # Try Supabase Storage
        try:
            from app.db_client import get_supabase_client

            sb = get_supabase_client()
            storage_path = f"causal_reports/{filename}"
            sb.storage.from_("reports").upload(
                storage_path,
                pdf_bytes,
                {"content-type": "application/pdf"},
            )
            url_resp = sb.storage.from_("reports").get_public_url(storage_path)
            logger.info("PDF uploaded to Supabase Storage: %s", url_resp)
            return url_resp
        except Exception as exc:
            logger.warning(
                "Supabase Storage upload failed (%s), saving locally",
                exc,
            )

        # Fallback: save to local reports directory
        reports_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "reports",
        )
        os.makedirs(reports_dir, exist_ok=True)
        filepath = os.path.join(reports_dir, filename)
        with open(filepath, "wb") as f:
            f.write(pdf_bytes)

        logger.info("PDF saved locally: %s", filepath)
        return f"file://{filepath}"

    # ------------------------------------------------------------------
    # Store report reference in database
    # ------------------------------------------------------------------

    async def _store_report_ref(self, disaster_id: str, report_url: str) -> None:
        """Persist audit report metadata in the database."""
        from app.database import db

        try:
            await (
                db.table("causal_audit_reports")
                .insert(
                    {
                        "disaster_id": disaster_id,
                        "report_url": report_url,
                        "generated_at": datetime.now(UTC).isoformat(),
                        "status": "completed",
                    }
                )
                .async_execute()
            )
        except Exception as exc:
            logger.error("Failed to store report reference: %s", exc)


# ---------------------------------------------------------------------------
# Hook for auto-generating reports on status change to "resolved"
# ---------------------------------------------------------------------------


async def on_disaster_resolved(disaster: dict) -> str | None:
    """Call this when a disaster status transitions to ``resolved``.

    Returns the report URL on success, or None on failure.
    """
    try:
        generator = CausalAuditReportGenerator()
        url = await generator.generate(disaster)
        return url
    except Exception as exc:
        logger.error(
            "Auto-generation of causal audit report failed for %s: %s",
            disaster.get("id"),
            exc,
        )
        return None
