"""
Training script for the GAT-based resource allocator.

Generates synthetic disaster scenarios, computes optimal assignments via
an ILP solver (PuLP), and trains the ``GATAllocator`` to reproduce those
assignments in a supervised fashion.

Usage
-----
    python -m ml.train_gat [--epochs 80] [--scenarios 500] [--lr 1e-3]
"""

from __future__ import annotations

import argparse
import logging
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pulp
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam
from torch.optim.lr_scheduler import CosineAnnealingLR

from app.services.distance import haversine
from ml.gat_model import (
    DEFAULT_CHECKPOINT,
    GATAllocator,
    save_checkpoint,
)
from ml.graph_builder import (
    RESOURCE_TYPES,
    NgoNode,
    VictimNode,
    build_graph,
)

logger = logging.getLogger(__name__)

# ── Synthetic data generation ────────────────────────────────────────────

# Geographic bounding box (roughly continental US for variety)
_LAT_RANGE = (25.0, 48.0)
_LON_RANGE = (-125.0, -67.0)


def _random_lat_lon(
    center_lat: float | None = None,
    center_lon: float | None = None,
    spread: float = 0.5,
) -> Tuple[float, float]:
    """Return a random (lat, lon) optionally near a centre point."""
    if center_lat is not None and center_lon is not None:
        lat = center_lat + random.uniform(-spread, spread)
        lon = center_lon + random.uniform(-spread, spread)
    else:
        lat = random.uniform(*_LAT_RANGE)
        lon = random.uniform(*_LON_RANGE)
    return (round(lat, 5), round(lon, 5))


def generate_scenario(
    n_victims: int | None = None,
    n_ngos: int | None = None,
    radius_km: float = 50.0,
) -> Tuple[List[VictimNode], List[NgoNode]]:
    """
    Generate a single synthetic disaster scenario.

    Returns victim and NGO node lists.
    """
    if n_victims is None:
        n_victims = random.randint(5, 25)
    if n_ngos is None:
        n_ngos = random.randint(3, 12)

    # Disaster epicentre
    epicentre = _random_lat_lon()

    victims: List[VictimNode] = []
    for i in range(n_victims):
        lat, lon = _random_lat_lon(epicentre[0], epicentre[1], spread=0.4)
        victims.append(
            VictimNode(
                id=f"v_{i}",
                lat=lat,
                lon=lon,
                priority_score=round(random.uniform(1, 10), 2),
                medical_needs_encoded=round(random.random(), 2),
                hours_since_request=round(random.uniform(0.1, 72.0), 2),
                resource_type=random.choice(RESOURCE_TYPES),
            )
        )

    ngos: List[NgoNode] = []
    for i in range(n_ngos):
        lat, lon = _random_lat_lon(epicentre[0], epicentre[1], spread=0.6)
        n_types = random.randint(1, 5)
        avail = random.sample(RESOURCE_TYPES, n_types)
        ngos.append(
            NgoNode(
                id=f"n_{i}",
                lat=lat,
                lon=lon,
                capacity_score=round(random.uniform(0.1, 1.0), 2),
                available_resource_types=avail,
                avg_response_time_hours=round(random.uniform(0.5, 12.0), 2),
                current_load_ratio=round(random.uniform(0.0, 0.9), 2),
            )
        )

    return victims, ngos


# ── ILP optimal assignment ───────────────────────────────────────────────


def solve_optimal_assignment(
    victims: List[VictimNode],
    ngos: List[NgoNode],
    radius_km: float = 50.0,
) -> List[Tuple[int, int]]:
    """
    Compute the optimal one-to-one victim→NGO assignment using an ILP solver.

    The objective maximises:
        Σ  x[v,n] * (priority_score × match_score / (1 + distance))

    Subject to:
        - Each victim assigned to at most one NGO.
        - Each NGO assigned to at most one victim (capacity = 1 per scenario).
        - Only edges within ``radius_km`` are eligible.

    Returns a list of ``(victim_idx, ngo_idx)`` pairs.
    """
    n_v = len(victims)
    n_n = len(ngos)

    prob = pulp.LpProblem("OptimalAssignment", pulp.LpMaximize)

    # Decision variables
    x = {}
    for vi in range(n_v):
        for ni in range(n_n):
            x[vi, ni] = pulp.LpVariable(f"x_{vi}_{ni}", cat=pulp.LpBinary)

    # Pre-compute scores
    obj_terms = []
    feasible_pairs = set()
    for vi, v in enumerate(victims):
        for ni, n in enumerate(ngos):
            dist = haversine(v.lat, v.lon, n.lat, n.lon)
            if dist > radius_km:
                prob += x[vi, ni] == 0, f"infeasible_{vi}_{ni}"
                continue
            feasible_pairs.add((vi, ni))

            # Resource-type match
            v_lower = v.resource_type.lower()
            n_lower = {t.lower() for t in n.available_resource_types}
            match = 1.0 if v_lower in n_lower else 0.3

            # Score: priority × match × capacity / (1 + distance)
            score = (
                v.priority_score
                * match
                * n.capacity_score
                / (1.0 + dist)
            )
            obj_terms.append(x[vi, ni] * score)

    if not obj_terms:
        return []

    prob += pulp.lpSum(obj_terms), "Objective"

    # Each victim assigned at most once
    for vi in range(n_v):
        prob += pulp.lpSum(x[vi, ni] for ni in range(n_n)) <= 1, f"v_{vi}"

    # Each NGO assigned at most once
    for ni in range(n_n):
        prob += pulp.lpSum(x[vi, ni] for vi in range(n_v)) <= 1, f"n_{ni}"

    solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=10)
    prob.solve(solver)

    assignments: List[Tuple[int, int]] = []
    if prob.status == pulp.constants.LpStatusOptimal:
        for (vi, ni) in feasible_pairs:
            val = pulp.value(x[vi, ni])
            if val is not None and val > 0.5:
                assignments.append((vi, ni))

    return assignments


# ── Dataset construction ─────────────────────────────────────────────────


def build_training_sample(
    victims: List[VictimNode],
    ngos: List[NgoNode],
    radius_km: float = 50.0,
) -> Optional[Dict[str, Any]]:
    """
    Build a single training sample: graph + binary edge labels from ILP.

    Returns None if there are no feasible edges.
    """
    data = build_graph(victims, ngos, radius_km=radius_km)
    edge_index = data["victim", "requests", "ngo"].edge_index

    if edge_index.size(1) == 0:
        return None

    # Solve optimal assignment
    optimal = solve_optimal_assignment(victims, ngos, radius_km=radius_km)
    optimal_set = set(optimal)

    # Build per-edge binary labels
    labels = torch.zeros(edge_index.size(1), dtype=torch.float32)
    for e in range(edge_index.size(1)):
        vi = edge_index[0, e].item()
        ni = edge_index[1, e].item()
        if (vi, ni) in optimal_set:
            labels[e] = 1.0

    return {"data": data, "labels": labels}


# ── Training loop ────────────────────────────────────────────────────────


def train(
    n_scenarios: int = 500,
    epochs: int = 80,
    lr: float = 1e-3,
    radius_km: float = 50.0,
    hidden: int = 64,
    heads: int = 4,
    dropout: float = 0.2,
    checkpoint_path: str | None = None,
    seed: int = 42,
) -> GATAllocator:
    """
    Train the GAT allocator on synthetic ILP-labelled scenarios.

    Parameters
    ----------
    n_scenarios : number of synthetic scenarios to generate.
    epochs : training epochs over the full dataset.
    lr : learning rate.
    radius_km : edge radius for graph construction.
    hidden, heads, dropout : model hyperparameters.
    checkpoint_path : where to save the trained model.
    seed : random seed for reproducibility.

    Returns
    -------
    The trained ``GATAllocator``.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    logger.info("Generating %d synthetic scenarios …", n_scenarios)
    dataset: List[Dict[str, Any]] = []
    for i in range(n_scenarios):
        victims, ngos = generate_scenario()
        sample = build_training_sample(victims, ngos, radius_km=radius_km)
        if sample is not None:
            dataset.append(sample)
        if (i + 1) % 100 == 0:
            logger.info("  generated %d / %d  (usable: %d)", i + 1, n_scenarios, len(dataset))

    if not dataset:
        raise RuntimeError("No usable training samples generated")

    logger.info("Usable samples: %d / %d", len(dataset), n_scenarios)

    # ── Split 80/20 ──────────────────────────────────────────────────
    split = int(len(dataset) * 0.8)
    train_set = dataset[:split]
    val_set = dataset[split:]
    logger.info("Train: %d  Val: %d", len(train_set), len(val_set))

    # ── Model / optim ────────────────────────────────────────────────
    model = GATAllocator(
        hidden=hidden, heads=heads, dropout=dropout,
    )
    optimiser = Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = CosineAnnealingLR(optimiser, T_max=epochs, eta_min=lr * 0.01)

    best_val_loss = float("inf")
    patience_counter = 0
    patience = 15

    for epoch in range(1, epochs + 1):
        # ── Train ────────────────────────────────────────────────────
        model.train()
        random.shuffle(train_set)
        train_loss_sum = 0.0
        train_count = 0

        for sample in train_set:
            data = sample["data"]
            labels = sample["labels"]

            logits = model(data)
            # Weighted BCE to handle class imbalance (few positives)
            n_pos = labels.sum().item()
            n_neg = labels.numel() - n_pos
            pos_weight = torch.tensor([max(n_neg / max(n_pos, 1), 1.0)])
            loss = F.binary_cross_entropy_with_logits(
                logits, labels, pos_weight=pos_weight,
            )

            optimiser.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimiser.step()

            train_loss_sum += loss.item()
            train_count += 1

        scheduler.step()
        avg_train = train_loss_sum / max(train_count, 1)

        # ── Validate ─────────────────────────────────────────────────
        model.eval()
        val_loss_sum = 0.0
        val_count = 0
        with torch.no_grad():
            for sample in val_set:
                data = sample["data"]
                labels = sample["labels"]
                logits = model(data)
                n_pos = labels.sum().item()
                n_neg = labels.numel() - n_pos
                pos_weight = torch.tensor([max(n_neg / max(n_pos, 1), 1.0)])
                loss = F.binary_cross_entropy_with_logits(
                    logits, labels, pos_weight=pos_weight,
                )
                val_loss_sum += loss.item()
                val_count += 1

        avg_val = val_loss_sum / max(val_count, 1)

        if epoch % 5 == 0 or epoch == 1:
            logger.info(
                "Epoch %3d/%d  train_loss=%.4f  val_loss=%.4f  lr=%.2e",
                epoch, epochs, avg_train, avg_val,
                optimiser.param_groups[0]["lr"],
            )

        # ── Early stopping ───────────────────────────────────────────
        if avg_val < best_val_loss:
            best_val_loss = avg_val
            patience_counter = 0
            # Save best
            ckpt = Path(checkpoint_path or DEFAULT_CHECKPOINT)
            save_checkpoint(model, ckpt)
        else:
            patience_counter += 1
            if patience_counter >= patience:
                logger.info("Early stopping at epoch %d", epoch)
                break

    # Reload best weights
    ckpt = Path(checkpoint_path or DEFAULT_CHECKPOINT)
    if ckpt.exists():
        model.load_state_dict(torch.load(ckpt, map_location="cpu", weights_only=True))
        logger.info("Reloaded best checkpoint (val_loss=%.4f)", best_val_loss)

    logger.info("Training complete.")
    return model


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    parser = argparse.ArgumentParser(description="Train GAT resource allocator")
    parser.add_argument("--scenarios", type=int, default=500, help="Number of synthetic scenarios")
    parser.add_argument("--epochs", type=int, default=80, help="Training epochs")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    parser.add_argument("--hidden", type=int, default=64, help="Hidden dimension")
    parser.add_argument("--heads", type=int, default=4, help="Attention heads per layer")
    parser.add_argument("--dropout", type=float, default=0.2, help="Dropout rate")
    parser.add_argument("--radius", type=float, default=50.0, help="Edge radius in km")
    parser.add_argument("--checkpoint", type=str, default=None, help="Checkpoint path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    train(
        n_scenarios=args.scenarios,
        epochs=args.epochs,
        lr=args.lr,
        radius_km=args.radius,
        hidden=args.hidden,
        heads=args.heads,
        dropout=args.dropout,
        checkpoint_path=args.checkpoint,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
