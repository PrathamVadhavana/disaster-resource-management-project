"""
Causal AI API router — counterfactual analysis & causal audit endpoints.

Endpoints
─────────
POST /api/causal/counterfactual   – Run a counterfactual "what-if" query
GET  /api/causal/effects           – Pre-computed ATE estimates
GET  /api/causal/graph             – Return the causal DAG edges
POST /api/causal/audit/{disaster_id} – Generate a Causal Audit Report PDF
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import db
from app.dependencies import get_current_user

logger = logging.getLogger("causal_router")

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class InterventionInput(BaseModel):
    variable: str = Field(..., description="Causal variable to intervene on")
    new_value: float = Field(..., description="Counterfactual value to set")


class CounterfactualRequest(BaseModel):
    disaster_id: str = Field(..., description="Disaster record ID")
    intervention: InterventionInput
    outcome_variable: str = Field(
        "casualties",
        description="Outcome to predict (casualties or economic_damage_usd)",
    )


class CounterfactualResponse(BaseModel):
    disaster_id: str
    original_casualties: float
    counterfactual_casualties: float
    difference: float
    confidence_interval: list[float]
    explanation: str


class CausalEffectResponse(BaseModel):
    treatment: str
    outcome: str
    method: str
    ate: float
    p_value: Optional[float]
    confidence_interval: list[float]
    refutation_passed: Optional[bool]
    refutation_p_value: Optional[float]


# ---------------------------------------------------------------------------
# Lazy singleton for the causal model
# ---------------------------------------------------------------------------

_causal_model = None


async def _get_causal_model():
    """Lazily initialise a shared DisasterCausalModel instance.

    Uses well-calibrated synthetic data by default. Real DB disaster records
    typically lack the causal-specific columns (response_time_hours,
    resource_availability, ngo_proximity_km, resource_quality_score), which
    would create zero-variance data and break the regression models.

    When the DB *does* have records with real causal fields, we blend them
    with synthetic data to ensure sufficient variance for estimation.
    """
    global _causal_model
    if _causal_model is None:
        from ml.causal_model import DisasterCausalModel, generate_synthetic_data
        import pandas as pd

        CAUSAL_FIELDS = [
            "response_time_hours", "resource_availability",
            "ngo_proximity_km", "resource_quality_score",
        ]

        blended_data = None
        try:
            from app.database import db_admin
            disasters = (await db_admin.table("disasters").select("*").async_execute()).data or []
            if disasters:
                rows = []
                for d in disasters:
                    # Only include records that have at least one real causal field
                    has_real_field = any(d.get(f) is not None for f in CAUSAL_FIELDS)
                    if not has_real_field:
                        continue
                    rows.append({
                        "weather_severity": float(d.get("severity_score") or 5.0),
                        "disaster_type": float(hash(d.get("type", "")) % 10 + 1),
                        "response_time_hours": float(d["response_time_hours"]) if d.get("response_time_hours") is not None else None,
                        "resource_availability": float(d["resource_availability"]) if d.get("resource_availability") is not None else None,
                        "ngo_proximity_km": float(d["ngo_proximity_km"]) if d.get("ngo_proximity_km") is not None else None,
                        "resource_quality_score": float(d["resource_quality_score"]) if d.get("resource_quality_score") is not None else None,
                        "casualties": float(d.get("casualties") or 0),
                        "economic_damage_usd": float(d.get("economic_damage_usd") or 0),
                    })

                if rows:
                    real_df = pd.DataFrame(rows)
                    # Fill any remaining NaN values from synthetic distribution
                    synthetic = generate_synthetic_data(n=2000)
                    for col in real_df.columns:
                        if real_df[col].isna().any():
                            real_df[col] = real_df[col].fillna(synthetic[col].sample(len(real_df), replace=True).values)
                    # Blend: real data + synthetic to ensure enough variance
                    blended_data = pd.concat([synthetic, real_df], ignore_index=True)
                    logger.info(
                        "Causal model blending %d real + %d synthetic observations",
                        len(real_df), len(synthetic),
                    )
        except Exception as e:
            logger.warning("Could not load real data for causal model: %s", e)

        _causal_model = DisasterCausalModel(data=blended_data)
    return _causal_model


# ---------------------------------------------------------------------------
# Helper – extract causal observation from a disaster record
# ---------------------------------------------------------------------------

def _disaster_to_observation(disaster: dict) -> dict[str, float]:
    """Map a disaster document to the causal model's variables.

    Missing fields are filled with domain-reasonable defaults.
    """
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/counterfactual",
    response_model=CounterfactualResponse,
    summary="Counterfactual what-if analysis",
)
async def counterfactual_analysis(
    body: CounterfactualRequest,
    user: dict = Depends(get_current_user),
):
    """Run a counterfactual query for a specific disaster.

    Given a recorded disaster and a hypothetical intervention
    (e.g. *"What if resource_availability had been 1.5?"*), estimate
    what the outcome (casualties / economic_damage) would have been.
    """
    # 1. Fetch disaster record
    try:
        result = (
            await db.table("disasters")
            .select("*")
            .eq("id", body.disaster_id)
            .maybe_single()
            .async_execute()
        )
        disaster = result.data
    except Exception as exc:
        logger.error("DB error fetching disaster %s: %s", body.disaster_id, exc)
        raise HTTPException(status_code=500, detail="Database error")

    if not disaster:
        raise HTTPException(status_code=404, detail="Disaster not found")

    # 2. Build observation vector
    observation = _disaster_to_observation(disaster)

    # 3. Run counterfactual
    try:
        cm = await _get_causal_model()
        cf = cm.counterfactual(
            observation=observation,
            intervention_var=body.intervention.variable,
            new_value=body.intervention.new_value,
            outcome_var=body.outcome_variable,
        )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as exc:
        logger.error("Counterfactual error: %s", exc)
        raise HTTPException(status_code=500, detail="Counterfactual estimation failed")

    return CounterfactualResponse(
        disaster_id=body.disaster_id,
        original_casualties=cf.original_value,
        counterfactual_casualties=cf.counterfactual_value,
        difference=cf.difference,
        confidence_interval=list(cf.confidence_interval),
        explanation=cf.explanation,
    )


@router.get(
    "/effects",
    summary="Pre-computed causal effect estimates",
)
async def get_causal_effects(
    user: dict = Depends(get_current_user),
):
    """Return ATE estimates for the two primary causal questions:

    1. response_time_hours → casualties
    2. resource_availability → economic_damage_usd

    Includes placebo-refutation results.
    """
    cm = await _get_causal_model()
    try:
        rt_cas = cm.estimate_response_time_on_casualties()
        ra_dmg = cm.estimate_resource_availability_on_damage()
    except Exception as exc:
        logger.error("Causal estimation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Estimation failed")

    return {
        "estimates": [rt_cas.to_dict(), ra_dmg.to_dict()],
    }


@router.get(
    "/graph",
    summary="Causal DAG structure",
)
async def get_causal_graph(
    user: dict = Depends(get_current_user),
):
    """Return nodes and directed edges of the causal DAG for visualisation."""
    from ml.causal_model import CAUSAL_NODES, CAUSAL_EDGES

    return {
        "nodes": CAUSAL_NODES,
        "edges": [{"source": s, "target": t} for s, t in CAUSAL_EDGES],
    }


@router.post(
    "/audit/{disaster_id}",
    summary="Generate Causal Audit Report",
)
async def generate_audit_report(
    disaster_id: str,
    user: dict = Depends(get_current_user),
):
    """Trigger generation of a Causal Audit Report PDF for a resolved disaster.

    The PDF is uploaded to Supabase Storage and its URL is returned.
    """
    # 1. Fetch disaster
    try:
        result = (
            await db.table("disasters")
            .select("*")
            .eq("id", disaster_id)
            .maybe_single()
            .async_execute()
        )
        disaster = result.data
    except Exception as exc:
        logger.error("DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error")

    if not disaster:
        raise HTTPException(status_code=404, detail="Disaster not found")

    # 2. Generate report
    try:
        from app.services.audit_report_generator import CausalAuditReportGenerator

        generator = CausalAuditReportGenerator()
        report_url = await generator.generate(disaster)
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Report generation failed")

    return {
        "disaster_id": disaster_id,
        "report_url": report_url,
        "status": "generated",
    }
