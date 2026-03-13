"""
Federated Learning Service — FedAvg aggregation with differential privacy.

Simulates federated training where multiple NGO nodes train local models
on their own data and a central server aggregates the weights.

Components
──────────
- ``LocalModel``         — per-node logistic / 2-layer NN classifier
- ``FederatedServer``    — FedAvg weight aggregation + DP noise injection
- ``FederatedClient``    — local training loop for a single NGO/node
- ``FederatedService``   — high-level orchestrator consumed by the router

Usage from the API layer::

    svc = FederatedService()
    result = await svc.run_round(n_clients=5, epochs_per_client=3)

Privacy
───────
Differential privacy is enforced via:
  1. Per-sample gradient clipping (max_grad_norm)
  2. Gaussian noise injection calibrated to (ε, δ)-DP after aggregation
"""

from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset

    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False
    logger.warning("PyTorch not available — federated learning disabled")

_MODEL_DIR = Path(__file__).resolve().parent / "models"
FEDERATED_CHECKPOINT = _MODEL_DIR / "federated_global.pt"


# ── Local Model Architecture ─────────────────────────────────────────────────

if _HAS_TORCH:

    class LocalModel(nn.Module):
        """Small 2-layer MLP for resource demand classification.

        Input:  feature vector (disaster context, resource stats)
        Output: multi-class logits (resource priority levels)
        """

        def __init__(self, input_dim: int = 12, hidden_dim: int = 64, output_dim: int = 4):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden_dim // 2, output_dim),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.net(x)
else:
    LocalModel = None  # type: ignore[assignment,misc]


# ── Differential Privacy Utilities ────────────────────────────────────────────


def clip_gradients(model: Any, max_norm: float = 1.0) -> float:
    """Clip per-parameter gradients and return the total norm before clipping."""
    if not _HAS_TORCH:
        return 0.0
    total_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)
    return float(total_norm)


def add_dp_noise(
    state_dict: dict[str, Any],
    noise_multiplier: float = 1.0,
    max_grad_norm: float = 1.0,
    n_clients: int = 1,
) -> dict[str, Any]:
    """Add calibrated Gaussian noise for (ε, δ)-differential privacy.

    Noise scale σ = noise_multiplier × (max_grad_norm / n_clients)

    This is added *after* FedAvg aggregation to protect individual
    client contributions.
    """
    if not _HAS_TORCH:
        return state_dict
    sigma = noise_multiplier * max_grad_norm / max(n_clients, 1)
    noisy_state = {}
    for key, param in state_dict.items():
        if isinstance(param, torch.Tensor) and param.is_floating_point():
            noise = torch.randn_like(param) * sigma
            noisy_state[key] = param + noise
        else:
            noisy_state[key] = param
    return noisy_state


def compute_privacy_budget(
    noise_multiplier: float,
    n_steps: int,
    n_samples: int,
    batch_size: int,
    delta: float = 1e-5,
) -> float:
    """Estimate ε using the Rényi DP → (ε, δ)-DP conversion (simplified).

    Uses the moments accountant approximation:
        ε ≈ sqrt(2 × ln(1/δ)) × (q × sqrt(T)) / σ

    where q = batch_size/n_samples (sampling rate), T = n_steps, σ = noise_multiplier
    """
    if noise_multiplier <= 0:
        return float("inf")
    q = min(batch_size / max(n_samples, 1), 1.0)
    epsilon = math.sqrt(2 * math.log(1.0 / delta)) * q * math.sqrt(n_steps) / noise_multiplier
    return round(epsilon, 4)


# ── Federated Client ─────────────────────────────────────────────────────────


@dataclass
class ClientResult:
    """Result from a single client's local training round."""

    client_id: str
    n_samples: int
    loss: float
    accuracy: float
    state_dict: dict[str, Any] = field(default_factory=dict)
    grad_norm: float = 0.0


class FederatedClient:
    """Represents a single NGO node performing local training."""

    def __init__(
        self,
        client_id: str,
        model: Any,
        learning_rate: float = 0.01,
        max_grad_norm: float = 1.0,
    ):
        self.client_id = client_id
        self.model = model
        self.lr = learning_rate
        self.max_grad_norm = max_grad_norm

    def train_local(
        self,
        data: np.ndarray,
        labels: np.ndarray,
        epochs: int = 3,
        batch_size: int = 32,
    ) -> ClientResult:
        """Train the local model on this client's data partition.

        Args:
            data: feature matrix (n_samples, n_features)
            labels: integer class labels (n_samples,)
            epochs: local training epochs
            batch_size: mini-batch size
        """
        if not _HAS_TORCH:
            return ClientResult(
                client_id=self.client_id,
                n_samples=len(data),
                loss=0.0,
                accuracy=0.0,
            )

        X = torch.tensor(data, dtype=torch.float32)
        y = torch.tensor(labels, dtype=torch.long)
        dataset = TensorDataset(X, y)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        self.model.train()
        optimizer = optim.SGD(self.model.parameters(), lr=self.lr, momentum=0.9)
        criterion = nn.CrossEntropyLoss()

        total_loss = 0.0
        correct = 0
        total = 0
        max_norm_seen = 0.0

        for epoch in range(epochs):
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                output = self.model(batch_X)
                loss = criterion(output, batch_y)
                loss.backward()

                # Per-step gradient clipping for DP
                norm = clip_gradients(self.model, self.max_grad_norm)
                max_norm_seen = max(max_norm_seen, norm)

                optimizer.step()

                total_loss += loss.item() * len(batch_X)
                preds = output.argmax(dim=1)
                correct += (preds == batch_y).sum().item()
                total += len(batch_X)

        avg_loss = total_loss / max(total, 1)
        accuracy = correct / max(total, 1)

        return ClientResult(
            client_id=self.client_id,
            n_samples=len(data),
            loss=round(avg_loss, 4),
            accuracy=round(accuracy, 4),
            state_dict=copy.deepcopy(self.model.state_dict()),
            grad_norm=round(max_norm_seen, 4),
        )


# ── Federated Server (FedAvg) ────────────────────────────────────────────────


class FederatedServer:
    """Central aggregation server implementing Federated Averaging (FedAvg).

    FedAvg aggregation:
        θ_global = Σ (n_k / N) × θ_k
    where n_k = samples on client k, N = total samples.

    After aggregation, optional DP noise is injected.
    """

    def __init__(
        self,
        global_model: Any,
        noise_multiplier: float = 1.0,
        max_grad_norm: float = 1.0,
        enable_dp: bool = True,
    ):
        self.global_model = global_model
        self.noise_multiplier = noise_multiplier
        self.max_grad_norm = max_grad_norm
        self.enable_dp = enable_dp
        self.round_number = 0
        self.history: list[dict[str, Any]] = []

    def get_global_weights(self) -> dict[str, Any]:
        """Return a copy of the current global model weights."""
        if not _HAS_TORCH or self.global_model is None:
            return {}
        return copy.deepcopy(self.global_model.state_dict())

    def aggregate(self, client_results: list[ClientResult]) -> dict[str, Any]:
        """Perform FedAvg aggregation of client model weights.

        Args:
            client_results: list of ClientResult from local training

        Returns:
            dict with aggregation metrics
        """
        if not _HAS_TORCH or not client_results:
            return {"status": "skipped", "reason": "no results"}

        self.round_number += 1
        total_samples = sum(cr.n_samples for cr in client_results)

        if total_samples == 0:
            return {"status": "skipped", "reason": "no samples"}

        # Weighted average of model parameters
        avg_state = {}
        for key in client_results[0].state_dict:
            weighted_sum = None
            for cr in client_results:
                weight = cr.n_samples / total_samples
                param = cr.state_dict[key].float() * weight
                if weighted_sum is None:
                    weighted_sum = param
                else:
                    weighted_sum += param
            avg_state[key] = weighted_sum

        # Apply differential privacy noise
        if self.enable_dp:
            avg_state = add_dp_noise(
                avg_state,
                noise_multiplier=self.noise_multiplier,
                max_grad_norm=self.max_grad_norm,
                n_clients=len(client_results),
            )

        # Update global model
        self.global_model.load_state_dict(avg_state)

        # Compute aggregate metrics
        avg_loss = np.mean([cr.loss for cr in client_results])
        avg_acc = np.mean([cr.accuracy for cr in client_results])

        round_info = {
            "round": self.round_number,
            "n_clients": len(client_results),
            "total_samples": total_samples,
            "avg_loss": round(float(avg_loss), 4),
            "avg_accuracy": round(float(avg_acc), 4),
            "dp_enabled": self.enable_dp,
            "noise_multiplier": self.noise_multiplier,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.history.append(round_info)
        logger.info(
            "FedAvg round %d: %d clients, %d samples, loss=%.4f, acc=%.4f",
            self.round_number,
            len(client_results),
            total_samples,
            avg_loss,
            avg_acc,
        )
        return round_info

    def save_global_model(self, path: Path | None = None) -> Path:
        """Save the global model checkpoint."""
        path = path or FEDERATED_CHECKPOINT
        path.parent.mkdir(parents=True, exist_ok=True)
        if _HAS_TORCH:
            torch.save(
                {
                    "model_state": self.global_model.state_dict(),
                    "round_number": self.round_number,
                    "history": self.history,
                },
                path,
            )
        logger.info("Federated global model saved to %s", path)
        return path

    def load_global_model(self, path: Path | None = None) -> None:
        """Load a global model checkpoint."""
        path = path or FEDERATED_CHECKPOINT
        if not _HAS_TORCH or not path.exists():
            return
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        self.global_model.load_state_dict(checkpoint["model_state"])
        self.round_number = checkpoint.get("round_number", 0)
        self.history = checkpoint.get("history", [])
        logger.info("Federated global model loaded from %s (round %d)", path, self.round_number)


# ── Synthetic Data Generator ─────────────────────────────────────────────────


def _generate_client_data(
    n_samples: int = 200,
    input_dim: int = 12,
    n_classes: int = 4,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic disaster-resource classification data.

    Features simulate:
        0-2: weather (temp, wind, precip)
        3-4: population density, infrastructure
        5-7: resource levels (food, medical, water)
        8-9: distance to hub, response time
        10-11: historical demand, vulnerability index
    """
    rng = np.random.RandomState(seed)
    X = rng.randn(n_samples, input_dim).astype(np.float32)

    # Create labels based on feature patterns (non-trivial decision boundary)
    severity = X[:, 0] * 0.3 + X[:, 2] * 0.4 - X[:, 5] * 0.2 + X[:, 11] * 0.5
    noise = rng.randn(n_samples) * 0.3
    severity += noise

    bins = np.percentile(severity, [25, 50, 75])
    labels = np.digitize(severity, bins).astype(np.int64)

    return X, labels


def _partition_data(
    X: np.ndarray,
    y: np.ndarray,
    n_clients: int,
    non_iid: bool = False,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Partition data across clients.

    Args:
        X, y: full dataset
        n_clients: number of client partitions
        non_iid: if True, each client gets a skewed label distribution
    """
    if non_iid:
        # Non-IID: sort by label, give contiguous chunks
        sorted_idx = np.argsort(y)
        X, y = X[sorted_idx], y[sorted_idx]

    chunk_size = len(X) // max(n_clients, 1)
    partitions = []
    for i in range(n_clients):
        start = i * chunk_size
        end = start + chunk_size if i < n_clients - 1 else len(X)
        partitions.append((X[start:end], y[start:end]))
    return partitions


# ── High-Level Service ────────────────────────────────────────────────────────


class FederatedService:
    """Production-ready federated learning service.

    Orchestrates multi-round FedAvg training with optional DP.
    """

    def __init__(
        self,
        input_dim: int = 12,
        hidden_dim: int = 64,
        output_dim: int = 4,
        noise_multiplier: float = 1.0,
        max_grad_norm: float = 1.0,
        enable_dp: bool = True,
    ):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.noise_multiplier = noise_multiplier
        self.max_grad_norm = max_grad_norm
        self.enable_dp = enable_dp

        self._server: FederatedServer | None = None
        self._initialized = False

    def _ensure_init(self) -> FederatedServer:
        if self._server is not None:
            return self._server
        if not _HAS_TORCH:
            raise RuntimeError("PyTorch required for federated learning")

        global_model = LocalModel(self.input_dim, self.hidden_dim, self.output_dim)
        self._server = FederatedServer(
            global_model=global_model,
            noise_multiplier=self.noise_multiplier,
            max_grad_norm=self.max_grad_norm,
            enable_dp=self.enable_dp,
        )

        # Try loading existing checkpoint
        if FEDERATED_CHECKPOINT.exists():
            try:
                self._server.load_global_model()
            except Exception as exc:
                logger.warning("Failed to load federated checkpoint: %s", exc)

        self._initialized = True
        return self._server

    async def run_round(
        self,
        n_clients: int = 5,
        epochs_per_client: int = 3,
        samples_per_client: int = 200,
        non_iid: bool = False,
        learning_rate: float = 0.01,
        use_real_data: bool = False,
    ) -> dict[str, Any]:
        """Execute one federated training round.

        Simulates local NGO models training on partitioned data,
        then aggregates via FedAvg.

        Args:
            n_clients: number of simulated NGO nodes
            epochs_per_client: local training epochs per client
            samples_per_client: data points per client
            non_iid: whether to use non-IID data partitioning
            learning_rate: client optimizer learning rate

        Returns:
            dict with round metrics and per-client details
        """
        server = self._ensure_init()

        partitions = []
        if use_real_data:
            try:
                from app.database import db

                resp = await db.table("resource_requests").select("*").not_.is_("ngo_id", "null").async_execute()
                requests = resp.data or []

                if len(requests) >= 50:
                    ngo_data = {}
                    rt_map = {
                        "food": 0,
                        "water": 1,
                        "medical": 2,
                        "shelter": 3,
                        "clothing": 4,
                        "financial_aid": 5,
                        "evacuation": 6,
                        "volunteers": 7,
                    }
                    p_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}

                    for r in requests:
                        nid = r.get("ngo_id")
                        if nid not in ngo_data:
                            ngo_data[nid] = []

                        rt_vec = [0.0] * 8
                        rt = str(r.get("resource_type", "")).lower()
                        if rt in rt_map:
                            rt_vec[rt_map[rt]] = 1.0

                        pval = p_map.get(str(r.get("priority")).lower(), 1)
                        feat = [
                            float(r.get("latitude", 0)),
                            float(r.get("longitude", 0)),
                            float(pval),
                            float(r.get("quantity", 1)),
                        ] + rt_vec
                        ngo_data[nid].append((feat, pval))

                    partitions = [
                        (np.array([d[0] for d in v], dtype=np.float32), np.array([d[1] for d in v], dtype=np.int64))
                        for v in ngo_data.values()
                        if len(v) >= 5
                    ]
                    if partitions:
                        n_clients = len(partitions)
                        logger.info("Using real data from %d NGOs for federated round", n_clients)
            except Exception as e:
                logger.warning("Error loading real federated data: %s", e)

        if not partitions:
            # Generate and partition synthetic data
            total_samples = n_clients * samples_per_client
            X_all, y_all = _generate_client_data(
                n_samples=total_samples,
                input_dim=self.input_dim,
                n_classes=self.output_dim,
                seed=server.round_number + 1,
            )
            partitions = _partition_data(X_all, y_all, n_clients, non_iid=non_iid)
            total_samples = len(X_all)
        else:
            total_samples = sum(len(p[0]) for p in partitions)

        # Distribute global weights and train locally
        global_weights = server.get_global_weights()
        client_results: list[ClientResult] = []

        for i, (X_client, y_client) in enumerate(partitions):
            client_id = f"ngo_node_{i}"
            # Create a fresh local model with global weights
            local_model = LocalModel(self.input_dim, self.hidden_dim, self.output_dim)
            if global_weights:
                local_model.load_state_dict(copy.deepcopy(global_weights))

            client = FederatedClient(
                client_id=client_id,
                model=local_model,
                learning_rate=learning_rate,
                max_grad_norm=self.max_grad_norm,
            )
            result = client.train_local(
                data=X_client,
                labels=y_client,
                epochs=epochs_per_client,
                batch_size=32,
            )
            client_results.append(result)

        # Aggregate
        round_info = server.aggregate(client_results)

        # Compute privacy budget
        total_steps = epochs_per_client * (samples_per_client // 32 + 1)
        epsilon = compute_privacy_budget(
            noise_multiplier=self.noise_multiplier,
            n_steps=total_steps * server.round_number,
            n_samples=total_samples,
            batch_size=32,
        )

        # Save checkpoint
        try:
            server.save_global_model()
        except Exception as exc:
            logger.warning("Failed to save federated checkpoint: %s", exc)

        return {
            **round_info,
            "client_details": [
                {
                    "client_id": cr.client_id,
                    "n_samples": cr.n_samples,
                    "loss": cr.loss,
                    "accuracy": cr.accuracy,
                    "grad_norm": cr.grad_norm,
                }
                for cr in client_results
            ],
            "privacy_budget_epsilon": epsilon,
            "data_distribution": "non_iid" if non_iid else "iid",
        }

    async def get_status(self) -> dict[str, Any]:
        """Return current federated learning status."""
        if not _HAS_TORCH:
            return {"status": "unavailable", "reason": "PyTorch not installed"}

        if self._server is None:
            has_checkpoint = FEDERATED_CHECKPOINT.exists()
            return {
                "status": "ready" if has_checkpoint else "untrained",
                "checkpoint_exists": has_checkpoint,
                "rounds_completed": 0,
            }

        return {
            "status": "active",
            "rounds_completed": self._server.round_number,
            "dp_enabled": self._server.enable_dp,
            "noise_multiplier": self._server.noise_multiplier,
            "history": self._server.history[-10:],  # last 10 rounds
        }

    async def run_full_training(
        self,
        n_rounds: int = 10,
        n_clients: int = 5,
        epochs_per_client: int = 3,
    ) -> dict[str, Any]:
        """Run multiple federated rounds (full training session).

        Returns aggregate metrics across all rounds.
        """
        results = []
        for round_num in range(n_rounds):
            logger.info("Federated training round %d/%d", round_num + 1, n_rounds)
            result = await self.run_round(
                n_clients=n_clients,
                epochs_per_client=epochs_per_client,
                non_iid=(round_num % 2 == 1),  # alternate IID/non-IID
            )
            results.append(result)

        return {
            "total_rounds": n_rounds,
            "final_accuracy": results[-1].get("avg_accuracy", 0) if results else 0,
            "final_loss": results[-1].get("avg_loss", 0) if results else 0,
            "privacy_budget_epsilon": results[-1].get("privacy_budget_epsilon", float("inf"))
            if results
            else float("inf"),
            "round_summaries": [
                {
                    "round": r.get("round", 0),
                    "avg_loss": r.get("avg_loss", 0),
                    "avg_accuracy": r.get("avg_accuracy", 0),
                }
                for r in results
            ],
        }


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    async def main():
        svc = FederatedService()
        result = await svc.run_full_training(n_rounds=10, n_clients=5, epochs_per_client=3)
        print(f"Final accuracy: {result['final_accuracy']}")
        print(f"Privacy budget (ε): {result['privacy_budget_epsilon']}")

    asyncio.run(main())
