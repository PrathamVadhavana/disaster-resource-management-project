"""
Advanced ML API Router — RL Allocation, Federated Learning, Multi-Agent, PINN.

Endpoints
─────────
POST /api/ml/rl-allocate          – RL-based resource allocation
GET  /api/ml/rl-status            – RL agent status
POST /api/ml/rl-train             – Trigger RL training (admin only)
POST /api/ml/federated/round      – Execute one federated learning round
GET  /api/ml/federated/status     – Federated learning status
POST /api/ml/federated/train      – Full federated training session (admin)
POST /api/ml/agent/query          – Multi-agent coordinated query
POST /api/ml/agent/stream         – Multi-agent SSE streaming query
GET  /api/ml/agent/status         – Multi-agent system status
POST /api/ml/pinn/predict         – PINN spread prediction
GET  /api/ml/pinn/status          – PINN model status
GET  /api/ml/health               – ML model health check
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.database import db
from app.dependencies import get_current_user, require_role

logger = logging.getLogger("advanced_ml_router")

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────


class RLAllocateRequest(BaseModel):
    disaster_id: str
    required_resources: list[dict[str, Any]] = Field(..., description="List of {type, quantity, priority} dicts")
    max_distance_km: float = Field(100.0, ge=1, le=1000)


class RLAllocateResponse(BaseModel):
    disaster_id: str
    allocations: list[dict[str, Any]]
    coverage_pct: float
    total_reward: float
    method: str
    steps: int


class FederatedRoundRequest(BaseModel):
    n_clients: int = Field(5, ge=2, le=20)
    epochs_per_client: int = Field(3, ge=1, le=20)
    samples_per_client: int = Field(200, ge=50, le=5000)
    non_iid: bool = False
    learning_rate: float = Field(0.01, ge=0.0001, le=1.0)


class FederatedTrainRequest(BaseModel):
    n_rounds: int = Field(10, ge=1, le=100)
    n_clients: int = Field(5, ge=2, le=20)
    epochs_per_client: int = Field(3, ge=1, le=20)


class AgentQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    disaster_id: str | None = None


class PINNPredictRequest(BaseModel):
    points: list[list[float]] = Field(..., description="List of [x, y, t] points")


class PINNTrainRequest(BaseModel):
    n_observations: int = Field(500, ge=100, le=5000)
    epochs: int = Field(500, ge=100, le=5000)
    diffusion: float = Field(0.02, ge=0.001, le=1.0)
    wind_x: float = Field(0.5, ge=-10, le=10)
    wind_y: float = Field(0.2, ge=-10, le=10)


class PINNGridRequest(BaseModel):
    x_range: list[float] = Field(..., min_length=2, max_length=2)
    y_range: list[float] = Field(..., min_length=2, max_length=2)
    time: float = Field(..., ge=0)
    resolution: int = Field(50, ge=10, le=200)


# ── Lazy singletons ───────────────────────────────────────────────────────────

_rl_allocator = None
_federated_service = None
_multi_agent = None
_pinn_model = None

_rl_training_status = {"status": "idle", "progress": 0, "result": None}


def _get_rl():
    global _rl_allocator
    if _rl_allocator is None:
        from ml.rl_allocator import RLAllocator

        _rl_allocator = RLAllocator()
    return _rl_allocator


def _get_federated():
    global _federated_service
    if _federated_service is None:
        from ml.federated_service import FederatedService

        _federated_service = FederatedService()
    return _federated_service


def _get_agent_system():
    global _multi_agent
    if _multi_agent is None:
        from ml.multi_agent import get_multi_agent_system

        _multi_agent = get_multi_agent_system()
    return _multi_agent


def _get_pinn():
    global _pinn_model
    if _pinn_model is None:
        from ml.pinn_spread import PINN_CHECKPOINT, PINNSpreadModel

        _pinn_model = PINNSpreadModel()
        if PINN_CHECKPOINT.exists():
            try:
                _pinn_model.load()
            except Exception as exc:
                logger.warning("Failed to load PINN checkpoint: %s", exc)
    return _pinn_model


async def _train_rl_background(n_episodes: int):
    global _rl_training_status, _rl_allocator
    _rl_training_status = {"status": "training", "progress": 0, "result": None}
    try:
        from ml.rl_allocator import RLAllocator

        allocator = RLAllocator()
        # Use the new train method that loads historical data from Supabase first
        # Note: train() is async, so we await it
        await allocator.train(db_client=db, n_episodes=n_episodes)
        _rl_training_status = {"status": "complete", "progress": 100, "result": "success"}
        _rl_allocator = None  # Force reload
    except Exception as e:
        _rl_training_status = {"status": "failed", "progress": 0, "result": str(e)}


# ── RL Allocation endpoints ──────────────────────────────────────────────────


@router.post("/rl-allocate", response_model=RLAllocateResponse)
async def rl_allocate(
    body: RLAllocateRequest,
    user: dict = Depends(require_role("admin", "ngo")),
):
    """Allocate resources using the Double-DQN reinforcement learning agent.

    Falls back to a greedy heuristic if the RL model has not been trained.
    """
    try:
        rl = _get_rl()

        # Fetch available resources
        resp = await db.table("resources").select("*").eq("status", "available").async_execute()
        raw_resources = resp.data or []

        # Build location cache
        location_cache: dict = {}
        location_ids = list({r.get("location_id", "") for r in raw_resources if r.get("location_id")})
        if location_ids:
            loc_resp = await db.table("locations").select("*").in_("id", location_ids[:30]).async_execute()
            for loc in loc_resp.data or []:
                location_cache[loc["id"]] = (
                    float(loc.get("latitude", 0)),
                    float(loc.get("longitude", 0)),
                )

        # Get disaster location
        zone_lat, zone_lon = 0.0, 0.0
        disaster_resp = (
            await db.table("disasters").select("*").eq("id", body.disaster_id).maybe_single().async_execute()
        )
        if disaster_resp.data:
            d_loc_id = disaster_resp.data.get("location_id", "")
            if d_loc_id in location_cache:
                zone_lat, zone_lon = location_cache[d_loc_id]

        result = rl.allocate(
            resources=raw_resources,
            requests=body.required_resources,
            disaster_id=body.disaster_id,
            location_cache=location_cache,
            zone_lat=zone_lat,
            zone_lon=zone_lon,
        )

        # Log each allocation to rl_allocation_log table
        try:
            for allocation in result.get("allocations", []):
                # Get resource type and quantity from the allocation
                resource_id = allocation.get("resource_id", "")
                request_id = allocation.get("request_id", "")
                
                # Fetch resource details for logging
                resource_detail = None
                if resource_id:
                    res_resp = await db.table("resources").select("*").eq("id", resource_id).maybe_single().async_execute()
                    if res_resp.data:
                        resource_detail = res_resp.data
                
                # Get quantity allocated (use quantity from resource if available)
                quantity_allocated = 1
                if resource_detail:
                    quantity_allocated = resource_detail.get("quantity", 1)
                
                # Get resource type
                resource_type = allocation.get("type", "unknown")
                if resource_detail:
                    resource_type = resource_detail.get("type", resource_type)
                
                # Allocation score (use coverage or total_reward as proxy)
                allocation_score = result.get("total_reward", 0.0)
                
                # Log to rl_allocation_log table
                log_entry = {
                    "id": str(uuid.uuid4()),
                    "disaster_id": body.disaster_id,
                    "resource_type": resource_type,
                    "quantity_allocated": quantity_allocated,
                    "allocation_score": allocation_score,
                    "actual_outcome": None,  # To be filled later
                    "allocated_at": datetime.now(timezone.utc).isoformat(),
                }
                
                await db.table("rl_allocation_log").insert(log_entry).async_execute()
                
            logger.info("Logged %d allocations to rl_allocation_log for disaster %s", 
                        len(result.get("allocations", [])), body.disaster_id)
        except Exception as log_err:
            logger.warning("Failed to log allocations to rl_allocation_log: %s", log_err)

        return RLAllocateResponse(**result)

    except Exception as exc:
        logger.error("RL allocation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"RL allocation failed: {exc}")


@router.get("/rl-status")
async def rl_status(user: dict = Depends(get_current_user)):
    """Check RL agent status."""
    try:
        rl = _get_rl()
        return {
            "status": "trained" if rl.is_trained else "untrained",
            "method": "double_dqn",
            "checkpoint_exists": rl._checkpoint.exists(),
        }
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


@router.post("/rl-train")
async def rl_train(
    background_tasks: BackgroundTasks,
    n_episodes: int = 2000,
    user: dict = Depends(require_role("admin")),
):
    """Trigger RL agent training in background (admin only)."""
    if _rl_training_status.get("status") == "training":
        raise HTTPException(status_code=409, detail="Training already in progress")

    background_tasks.add_task(_train_rl_background, min(n_episodes, 5000))
    return {"status": "training_started", "message": "RL training started in background"}


@router.get("/rl-training-status")
async def get_rl_training_status():
    """Get current status of background RL training."""
    return _rl_training_status


# ── Federated Learning endpoints ─────────────────────────────────────────────


@router.post("/federated/round")
async def federated_round(
    body: FederatedRoundRequest,
    user: dict = Depends(require_role("admin")),
):
    """Execute one round of federated learning with simulated NGO nodes."""
    try:
        svc = _get_federated()
        result = await svc.run_round(
            n_clients=body.n_clients,
            epochs_per_client=body.epochs_per_client,
            samples_per_client=body.samples_per_client,
            non_iid=body.non_iid,
            learning_rate=body.learning_rate,
        )
        return result
    except Exception as exc:
        logger.error("Federated round failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Federated round failed: {exc}")


@router.get("/federated/status")
async def federated_status(user: dict = Depends(get_current_user)):
    """Get federated learning status."""
    try:
        svc = _get_federated()
        return await svc.get_status()
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


@router.post("/federated/train")
async def federated_train(
    body: FederatedTrainRequest,
    user: dict = Depends(require_role("admin")),
):
    """Run full federated training session (admin only)."""
    try:
        svc = _get_federated()
        result = await svc.run_full_training(
            n_rounds=body.n_rounds,
            n_clients=body.n_clients,
            epochs_per_client=body.epochs_per_client,
        )
        return result
    except Exception as exc:
        logger.error("Federated training failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Federated training failed: {exc}")


# ── Multi-Agent endpoints ────────────────────────────────────────────────────


@router.post("/agent/query")
async def agent_query(
    body: AgentQueryRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a query to the multi-agent coordination system.

    The coordinator dispatches the query to specialist agents
    (Predictor, Allocator, Analyst, Responder) and returns
    the synthesised response.
    """
    try:
        system = _get_agent_system()
        result = await system.process_query(
            query=body.query,
            disaster_id=body.disaster_id,
        )
        return result
    except Exception as exc:
        logger.error("Agent query failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent query failed: {exc}")


@router.post("/agent/stream")
async def agent_stream(
    body: AgentQueryRequest,
    user: dict = Depends(get_current_user),
):
    """Streaming multi-agent query — returns SSE events as each agent completes.

    Event types:
      - agent_start: an agent has begun processing
      - agent_result: an agent has completed with results
      - agent_error: an agent encountered an error
      - final: all agents complete, includes execution summary
    """
    system = _get_agent_system()

    async def event_generator():
        try:
            async for chunk in system.process_query_stream(
                query=body.query,
                disaster_id=body.disaster_id,
            ):
                yield f"data: {chunk}\n\n"
        except Exception as exc:
            logger.error("Agent stream error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/agent/status")
async def agent_status(user: dict = Depends(get_current_user)):
    """Get multi-agent system status."""
    try:
        system = _get_agent_system()
        return await system.get_status()
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


# ── PINN Spread endpoints ────────────────────────────────────────────────────


@router.post("/pinn/predict")
async def pinn_predict(
    body: PINNPredictRequest,
    user: dict = Depends(get_current_user),
):
    """Predict disaster spread intensity at given (x, y, t) points using PINN."""
    try:
        pinn = _get_pinn()
        if not pinn.is_trained:
            raise HTTPException(status_code=503, detail="PINN model not trained")
        points = [tuple(p) for p in body.points]
        predictions = pinn.predict(points)
        return {"predictions": predictions}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("PINN prediction failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"PINN prediction failed: {exc}")


@router.post("/pinn/predict-grid")
async def pinn_predict_grid(
    body: PINNGridRequest,
    user: dict = Depends(get_current_user),
):
    """Predict disaster spread on a 2D grid at a given time (for heatmap rendering)."""
    try:
        pinn = _get_pinn()
        if not pinn.is_trained:
            raise HTTPException(status_code=503, detail="PINN model not trained")
        result = pinn.predict_grid(
            x_range=tuple(body.x_range),
            y_range=tuple(body.y_range),
            t=body.time,
            resolution=body.resolution,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("PINN grid prediction failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"PINN grid prediction failed: {exc}")


@router.post("/pinn/train", summary="Train PINN model")
async def train_pinn(
    req: PINNTrainRequest,
    user: dict = Depends(require_role("admin")),
):
    """Train the PINN spread prediction model. Admin only."""
    try:
        from ml.pinn_spread import PINNSpreadModel, generate_synthetic_spread_data

        observations, terrain = generate_synthetic_spread_data(
            n_observations=req.n_observations,
            diffusion=req.diffusion,
            wind_x=req.wind_x,
            wind_y=req.wind_y,
        )

        pinn = PINNSpreadModel()
        result = pinn.train(observations, terrain, epochs=req.epochs)
        pinn.save()

        # Reset the global singleton so it reloads
        global _pinn_model
        _pinn_model = None

        return {
            "status": "trained",
            "epochs": req.epochs,
            "observations": req.n_observations,
            **result,
        }
    except Exception as e:
        raise HTTPException(500, f"PINN training failed: {str(e)}")


@router.get("/pinn/status")
async def pinn_status(user: dict = Depends(get_current_user)):
    """Get PINN model status."""
    try:
        pinn = _get_pinn()
        return {
            "status": "trained" if pinn.is_trained else "untrained",
            "model": "Physics-Informed Neural Network (advection-diffusion PDE)",
            "training_history_length": len(pinn._training_history),
        }
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


# ── GAT Matching ──────────────────────────────────────────────────────────────


class GATMatchRequest(BaseModel):
    disaster_id: str | None = None
    radius_km: float = Field(50.0, description="Max distance for edges")


@router.post("/gat/match")
async def gat_match(
    body: GATMatchRequest,
    user: dict = Depends(require_role("admin")),
):
    """Run GAT-based victim-NGO matching using graph attention network.

    Builds a bipartite graph from current approved requests and NGOs,
    runs GATAllocator inference, and returns optimal assignments via
    Hungarian algorithm. Falls back to distance-based matching if no
    trained checkpoint is available.
    """
    from app.database import db_admin

    try:
        # Fetch approved/under_review requests
        rq = db_admin.table("resource_requests").select("*").in_("status", ["approved", "under_review"])
        if body.disaster_id:
            rq = rq.eq("disaster_id", body.disaster_id)
        requests = (await rq.async_execute()).data or []

        # Fetch NGO users with location data
        ngos_resp = await db_admin.table("users").select("*").eq("role", "ngo").async_execute()
        ngos = ngos_resp.data or []

        if not requests or not ngos:
            return {"assignments": [], "method": "none", "reason": "No requests or NGOs found"}

        # Build victim and NGO nodes for graph
        from ml.graph_builder import RESOURCE_TYPES, NgoNode, VictimNode, build_graph

        victim_nodes = []
        for r in requests:
            rt = (r.get("resource_type") or "").lower()
            victim_nodes.append(
                VictimNode(
                    id=r["id"],
                    lat=float(r.get("latitude") or 0.0),
                    lon=float(r.get("longitude") or 0.0),
                    priority_score=5.0
                    if r.get("priority") == "medium"
                    else 10.0
                    if r.get("priority") == "high"
                    else 2.0,
                    medical_needs_encoded=1.0 if rt == "medical" else 0.0,
                    hours_since_request=0.0,
                    resource_type=rt,
                )
            )

        ngo_nodes = []
        for n in ngos:
            ngo_nodes.append(
                NgoNode(
                    id=n["id"],
                    lat=float(n.get("latitude") or 0.0),
                    lon=float(n.get("longitude") or 0.0),
                    capacity_score=0.8,
                    available_resource_types=[t.lower() for t in RESOURCE_TYPES[:5]],
                    avg_response_time_hours=2.0,
                    current_load_ratio=0.1,
                )
            )

        graph_data = build_graph(victim_nodes, ngo_nodes, radius_km=body.radius_km)

        # Try loading trained GAT model
        try:
            import torch

            from ml.gat_model import DEFAULT_CHECKPOINT, hungarian_assignment, load_checkpoint

            if DEFAULT_CHECKPOINT.exists():
                model = load_checkpoint()
                with torch.no_grad():
                    edge_probs = model(graph_data)
                assignments = hungarian_assignment(
                    edge_probs,
                    graph_data,
                    victim_ids=[v.id for v in victim_nodes],
                    ngo_ids=[n.id for n in ngo_nodes],
                )
                return {"assignments": assignments, "method": "gat", "total": len(assignments)}
        except Exception as e:
            logger.warning("GAT model unavailable, using distance fallback: %s", e)

        # Distance-based fallback assignment
        from app.services.distance import haversine

        assignments = []
        for v in victim_nodes:
            best_ngo = min(ngo_nodes, key=lambda n: haversine(v.lat, v.lon, n.lat, n.lon))
            dist = haversine(v.lat, v.lon, best_ngo.lat, best_ngo.lon)
            assignments.append(
                {
                    "victim_request_id": v.id,
                    "ngo_id": best_ngo.id,
                    "distance_km": round(dist, 2),
                }
            )
        return {"assignments": assignments, "method": "distance_fallback", "total": len(assignments)}

    except Exception as exc:
        logger.exception("GAT matching failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/gat/status")
async def gat_status(user: dict = Depends(get_current_user)):
    """Get GAT model status."""
    try:
        from ml.gat_model import DEFAULT_CHECKPOINT

        return {
            "status": "trained" if DEFAULT_CHECKPOINT.exists() else "untrained",
            "model": "Heterogeneous Graph Attention Network (GATv2)",
            "checkpoint_exists": DEFAULT_CHECKPOINT.exists(),
        }
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


# ── ML Health Check ──────────────────────────────────────────────────────────


@router.get("/health")
async def ml_health():
    """Comprehensive ML model health check.

    Lists all ML models and their load status. Use this at startup
    to verify which models are available and which need training.
    """
    models = {}

    # GAT model
    try:
        from ml.gat_model import DEFAULT_CHECKPOINT as GAT_CKPT

        models["gat_allocator"] = {
            "checkpoint_exists": GAT_CKPT.exists(),
            "status": "loaded" if GAT_CKPT.exists() else "needs_training",
            "checkpoint_path": str(GAT_CKPT),
        }
    except Exception as exc:
        models["gat_allocator"] = {"status": "error", "error": str(exc)}

    # RL allocator
    try:
        from ml.rl_allocator import DEFAULT_RL_CHECKPOINT

        models["rl_allocator"] = {
            "checkpoint_exists": DEFAULT_RL_CHECKPOINT.exists(),
            "status": "loaded" if DEFAULT_RL_CHECKPOINT.exists() else "needs_training",
            "checkpoint_path": str(DEFAULT_RL_CHECKPOINT),
        }
    except Exception as exc:
        models["rl_allocator"] = {"status": "error", "error": str(exc)}

    # Federated model
    try:
        from ml.federated_service import FEDERATED_CHECKPOINT

        models["federated_global"] = {
            "checkpoint_exists": FEDERATED_CHECKPOINT.exists(),
            "status": "loaded" if FEDERATED_CHECKPOINT.exists() else "needs_training",
            "checkpoint_path": str(FEDERATED_CHECKPOINT),
        }
    except Exception as exc:
        models["federated_global"] = {"status": "error", "error": str(exc)}

    # PINN model
    try:
        from ml.pinn_spread import PINN_CHECKPOINT

        models["pinn_spread"] = {
            "checkpoint_exists": PINN_CHECKPOINT.exists(),
            "status": "loaded" if PINN_CHECKPOINT.exists() else "needs_training",
            "checkpoint_path": str(PINN_CHECKPOINT),
        }
    except Exception as exc:
        models["pinn_spread"] = {"status": "error", "error": str(exc)}

    # NLP / DistilBERT
    try:
        nlp_model_dir = Path(__file__).resolve().parent.parent / "ml" / "models" / "nlp_triage"
        models["nlp_triage"] = {
            "checkpoint_exists": nlp_model_dir.exists(),
            "status": "loaded" if nlp_model_dir.exists() else "needs_training",
        }
    except Exception as exc:
        models["nlp_triage"] = {"status": "error", "error": str(exc)}

    # TFT model
    try:
        tft_path = Path(__file__).resolve().parent.parent / "ml" / "models" / "tft_severity.pt"
        models["tft_severity"] = {
            "checkpoint_exists": tft_path.exists(),
            "status": "loaded" if tft_path.exists() else "needs_training",
        }
    except Exception as exc:
        models["tft_severity"] = {"status": "error", "error": str(exc)}

    # DisasterGPT / RAG
    try:
        models["disaster_rag"] = {
            "status": "available",
            "description": "ChromaDB-backed RAG pipeline",
        }
    except Exception as exc:
        models["disaster_rag"] = {"status": "error", "error": str(exc)}

    # Summary
    n_loaded = sum(1 for m in models.values() if m.get("status") in ("loaded", "available"))
    n_total = len(models)

    return {
        "status": "healthy" if n_loaded > 0 else "degraded",
        "models_loaded": n_loaded,
        "models_total": n_total,
        "models": models,
    }


# ── Anomaly Detection Endpoints ─────────────────────────────────────


# Lazy singleton for anomaly service
_anomaly_service = None


def get_anomaly_service():
    """Get the anomaly detection service singleton."""
    global _anomaly_service
    if _anomaly_service is None:
        from app.services.anomaly_service import AnomalyDetectionService
        _anomaly_service = AnomalyDetectionService()
    return _anomaly_service


class AnomalyFeedbackRequest(BaseModel):
    alert_id: str
    status: str = Field(..., description="Status: 'false_positive' or 'resolved'")


class AnomalyDetectionResponse(BaseModel):
    success: bool
    message: str
    alerts_generated: int = 0
    details: dict | None = None


@router.post("/anomaly/build-baseline", response_model=dict)
async def build_anomaly_baseline():
    """
    Build the anomaly detection baseline model.
    
    Queries historical data and trains an Isolation Forest model
    to establish a baseline for anomaly detection.
    """
    service = get_anomaly_service()
    result = await service.build_baseline()
    return result


@router.post("/anomaly/rebuild-baseline", response_model=dict)
async def rebuild_anomaly_baseline():
    """
    Manually rebuild the anomaly detection baseline model.
    
    Useful when there's been significant changes in the data
    and you want to retrain from scratch.
    """
    service = get_anomaly_service()
    result = await service.rebuild_baseline()
    return result


@router.post("/anomaly/detect", response_model=AnomalyDetectionResponse)
async def run_anomaly_detection():
    """
    Manually trigger anomaly detection.
    
    Runs the full detection pipeline including:
    - Baseline deviation detection
    - Geographic surge detection
    - Traditional time-series anomaly detection
    """
    service = get_anomaly_service()
    alerts = await service.run_detection()
    
    return AnomalyDetectionResponse(
        success=True,
        message=f"Detection complete. Generated {len(alerts)} alerts.",
        alerts_generated=len(alerts),
        details={"alerts": alerts} if alerts else None
    )


@router.get("/anomaly/alerts", response_model=list)
async def get_anomaly_alerts(
    status: str | None = Query(None, description="Filter by status: active, acknowledged, resolved, false_positive"),
    severity: str | None = Query(None, description="Filter by severity: low, medium, high, critical"),
    anomaly_type: str | None = Query(None, description="Filter by anomaly type"),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(require_role("admin")),
):
    """
    Get anomaly alerts with optional filtering.
    
    Requires admin role.
    """
    service = get_anomaly_service()
    alerts = await service.get_all_alerts(
        status=status,
        severity=severity,
        limit=limit
    )
    
    if anomaly_type:
        alerts = [a for a in alerts if a.get("anomaly_type") == anomaly_type]
    
    return alerts


@router.post("/anomaly/feedback", response_model=dict)
async def submit_anomaly_feedback(
    body: AnomalyFeedbackRequest,
    admin: dict = Depends(require_role("admin")),
):
    """
    Submit feedback on an anomaly alert.
    
    - **false_positive**: Add to exclusion list, model stops flagging similar patterns
    - **resolved**: Mark as confirmed anomaly for future model refinement
    
    Requires admin role.
    """
    service = get_anomaly_service()
    user_id = admin.get("id", "unknown")
    
    result = await service.handle_feedback(
        alert_id=body.alert_id,
        status=body.status,
        user_id=user_id
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to process feedback"))
    
    return result


@router.get("/anomaly/status", response_model=dict)
async def get_anomaly_status():
    """
    Get the status of the anomaly detection system.
    
    Returns information about:
    - Whether baseline model is loaded
    - Number of exclusion entries
    - Number of confirmed anomalies
    """
    service = get_anomaly_service()
    
    from app.services.anomaly_service import BASELINE_MODEL_PATH, EXCLUSION_LIST_PATH, CONFIRMED_ANOMALIES_PATH
    
    return {
        "baseline_loaded": service._baseline_model is not None,
        "baseline_path": str(BASELINE_MODEL_PATH) if BASELINE_MODEL_PATH.exists() else None,
        "exclusion_count": len(service._exclusion_list),
        "confirmed_anomalies_count": len(service._confirmed_anomalies),
        "feature_columns": service._feature_columns
    }
