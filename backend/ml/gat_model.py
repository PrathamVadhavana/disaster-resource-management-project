"""
Graph Attention Network (GAT) for victim ↔ NGO resource assignment.

Architecture
------------
* 2-layer heterogeneous GAT (``HeteroConv`` wrapping ``GATv2Conv``) with
  4 attention heads per layer.
* A bilinear assignment head that scores every victim–NGO edge and outputs
  an assignment probability.
* Post-processing via the **Hungarian algorithm** (``scipy.optimize.linear_sum_assignment``)
  to enforce one-to-one matching.
* Optional SHAP-based feature-importance explanations per assignment.

The model operates on the ``HeteroData`` bipartite graph produced by
``ml.graph_builder.build_graph``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from scipy.optimize import linear_sum_assignment
    from torch_geometric.data import HeteroData
    from torch_geometric.nn import GATv2Conv, HeteroConv, Linear

    _HAS_GAT_DEPS = True
except ImportError:
    _HAS_GAT_DEPS = False
    logger.warning("torch_geometric or scipy not available — GAT allocator disabled")

# ── Paths ────────────────────────────────────────────────────────────────

_MODEL_DIR = Path(__file__).resolve().parent / "models"
DEFAULT_CHECKPOINT = _MODEL_DIR / "gat_allocator.pt"

# ── Dimensions (must agree with graph_builder) ───────────────────────────

VICTIM_IN_DIM = 13  # 5 scalar + 8 one-hot
NGO_IN_DIM = 13  # 3 scalar + 8 multi-hot + 2 scalar
EDGE_DIM = 3  # distance_km, travel_time_min, match_score


if _HAS_GAT_DEPS:
    # =====================================================================
    #  GAT Encoder
    # =====================================================================

    class HeteroGATEncoder(nn.Module):
        """
        Two-layer heterogeneous GATv2 encoder.

        Each layer uses ``HeteroConv`` to handle both (victim→ngo) and
        (ngo→victim) message-passing directions independently, then
        concatenates the multi-head outputs.
        """

        def __init__(
            self,
            victim_in: int = VICTIM_IN_DIM,
            ngo_in: int = NGO_IN_DIM,
            edge_dim: int = EDGE_DIM,
            hidden: int = 64,
            heads: int = 4,
            dropout: float = 0.2,
        ):
            super().__init__()
            self.dropout = dropout

            # ── Input projections (align dims before GAT) ────────────────
            self.victim_proj = Linear(victim_in, hidden)
            self.ngo_proj = Linear(ngo_in, hidden)

            # ── Layer 1 ──────────────────────────────────────────────────
            self.conv1 = HeteroConv(
                {
                    ("victim", "requests", "ngo"): GATv2Conv(
                        hidden,
                        hidden,
                        heads=heads,
                        edge_dim=edge_dim,
                        concat=True,
                        dropout=dropout,
                        add_self_loops=False,
                    ),
                    ("ngo", "serves", "victim"): GATv2Conv(
                        hidden,
                        hidden,
                        heads=heads,
                        edge_dim=edge_dim,
                        concat=True,
                        dropout=dropout,
                        add_self_loops=False,
                    ),
                },
                aggr="sum",
            )

            mid = hidden * heads  # concatenated multi-head output

            # ── Layer 2 ──────────────────────────────────────────────────
            self.conv2 = HeteroConv(
                {
                    ("victim", "requests", "ngo"): GATv2Conv(
                        mid,
                        hidden,
                        heads=heads,
                        edge_dim=edge_dim,
                        concat=False,
                        dropout=dropout,
                        add_self_loops=False,
                    ),
                    ("ngo", "serves", "victim"): GATv2Conv(
                        mid,
                        hidden,
                        heads=heads,
                        edge_dim=edge_dim,
                        concat=False,
                        dropout=dropout,
                        add_self_loops=False,
                    ),
                },
                aggr="sum",
            )

            self.out_dim = hidden  # final node embedding dimension

        def forward(self, data: HeteroData) -> dict[str, torch.Tensor]:
            x_dict = {
                "victim": F.elu(self.victim_proj(data["victim"].x)),
                "ngo": F.elu(self.ngo_proj(data["ngo"].x)),
            }

            edge_index_dict = {
                ("victim", "requests", "ngo"): data["victim", "requests", "ngo"].edge_index,
                ("ngo", "serves", "victim"): data["ngo", "serves", "victim"].edge_index,
            }

            edge_attr_dict = {
                ("victim", "requests", "ngo"): data["victim", "requests", "ngo"].edge_attr,
                ("ngo", "serves", "victim"): data["ngo", "serves", "victim"].edge_attr,
            }

            # Layer 1
            x_dict = self.conv1(x_dict, edge_index_dict, edge_attr_dict)
            x_dict = {k: F.elu(v) for k, v in x_dict.items()}
            x_dict = {k: F.dropout(v, p=self.dropout, training=self.training) for k, v in x_dict.items()}

            # Layer 2
            x_dict = self.conv2(x_dict, edge_index_dict, edge_attr_dict)
            x_dict = {k: F.elu(v) for k, v in x_dict.items()}

            return x_dict

    # =====================================================================
    #  Bilinear Assignment Head
    # =====================================================================

    class BilinearAssignmentHead(nn.Module):
        """
        Scores each (victim, ngo) pair with a bilinear product:

            score(v, n) = v^T W n + b

        Then applies sigmoid for probability interpretation.
        """

        def __init__(self, embed_dim: int, edge_dim: int = EDGE_DIM):
            super().__init__()
            # Bilinear interaction between victim and ngo embeddings
            self.bilinear = nn.Bilinear(embed_dim, embed_dim, 1)
            # Also incorporate edge features
            self.edge_mlp = nn.Sequential(
                nn.Linear(edge_dim, 16),
                nn.ReLU(),
                nn.Linear(16, 1),
            )
            self.combine = nn.Linear(2, 1)

        def forward(
            self,
            victim_emb: torch.Tensor,
            ngo_emb: torch.Tensor,
            edge_index: torch.Tensor,
            edge_attr: torch.Tensor,
        ) -> torch.Tensor:
            v_sel = victim_emb[edge_index[0]]  # (E, D)
            n_sel = ngo_emb[edge_index[1]]  # (E, D)

            bilinear_out = self.bilinear(v_sel, n_sel)  # (E, 1)
            edge_out = self.edge_mlp(edge_attr)  # (E, 1)
            combined = self.combine(torch.cat([bilinear_out, edge_out], dim=-1))  # (E, 1)
            return combined.squeeze(-1)  # (E,)

    # =====================================================================
    #  Full Model
    # =====================================================================

    class GATAllocator(nn.Module):
        """
        End-to-end GAT allocator: encoder + bilinear assignment head.
        """

        def __init__(
            self,
            victim_in: int = VICTIM_IN_DIM,
            ngo_in: int = NGO_IN_DIM,
            edge_dim: int = EDGE_DIM,
            hidden: int = 64,
            heads: int = 4,
            dropout: float = 0.2,
        ):
            super().__init__()
            self.encoder = HeteroGATEncoder(
                victim_in=victim_in,
                ngo_in=ngo_in,
                edge_dim=edge_dim,
                hidden=hidden,
                heads=heads,
                dropout=dropout,
            )
            self.assignment_head = BilinearAssignmentHead(
                embed_dim=self.encoder.out_dim,
                edge_dim=edge_dim,
            )

        def forward(self, data: HeteroData) -> torch.Tensor:
            """Return assignment logits for every victim→ngo edge."""
            x_dict = self.encoder(data)
            edge_index = data["victim", "requests", "ngo"].edge_index
            edge_attr = data["victim", "requests", "ngo"].edge_attr
            logits = self.assignment_head(x_dict["victim"], x_dict["ngo"], edge_index, edge_attr)
            return logits

        def predict_probs(self, data: HeteroData) -> torch.Tensor:
            """Return sigmoid probabilities for each edge."""
            self.eval()
            with torch.no_grad():
                logits = self.forward(data)
                return torch.sigmoid(logits)

    # =====================================================================
    #  Hungarian post-processing
    # =====================================================================

    def hungarian_assignment(
        edge_probs: torch.Tensor,
        data: HeteroData,
        victim_ids: list[str] = None,
        ngo_ids: list[str] = None,
    ) -> list[dict[str, Any]]:
        edge_index = data["victim", "requests", "ngo"].edge_index
        n_victims = data["victim"].x.size(0)
        n_ngos = data["ngo"].x.size(0)
        probs_np = edge_probs.cpu().numpy()

        cost = np.full((n_victims, n_ngos), 1e6, dtype=np.float64)
        for e in range(edge_index.size(1)):
            vi = edge_index[0, e].item()
            ni = edge_index[1, e].item()
            cost[vi, ni] = -probs_np[e]

        row_ind, col_ind = linear_sum_assignment(cost)

        assignments: list[dict[str, Any]] = []
        for vi, ni in zip(row_ind, col_ind):
            if cost[vi, ni] >= 1e5:
                continue

            res = {
                "victim_idx": int(vi),
                "ngo_idx": int(ni),
                "matching_score": float(-cost[vi, ni]),
            }
            if victim_ids and vi < len(victim_ids):
                res["victim_id"] = victim_ids[vi]
            if ngo_ids and ni < len(ngo_ids):
                res["ngo_id"] = ngo_ids[ni]

            assignments.append(res)

        return assignments

    # =====================================================================
    #  SHAP explanations
    # =====================================================================

    def explain_assignment(
        model: GATAllocator,
        data: HeteroData,
        victim_idx: int,
        ngo_idx: int,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        victim_feature_names = [
            "lat",
            "lon",
            "priority_score",
            "medical_needs",
            "hours_since_request",
            *[
                f"rtype_{rt}"
                for rt in [
                    "food",
                    "water",
                    "medical",
                    "shelter",
                    "clothing",
                    "financial_aid",
                    "evacuation",
                    "volunteers",
                ]
            ],
        ]
        ngo_feature_names = [
            "lat",
            "lon",
            "capacity_score",
            *[
                f"avail_{rt}"
                for rt in [
                    "food",
                    "water",
                    "medical",
                    "shelter",
                    "clothing",
                    "financial_aid",
                    "evacuation",
                    "volunteers",
                ]
            ],
            "avg_response_time",
            "current_load_ratio",
        ]
        edge_feature_names = ["distance_km", "travel_time_min", "match_score"]

        model.eval()

        v_x = data["victim"].x.clone().detach().requires_grad_(True)
        n_x = data["ngo"].x.clone().detach().requires_grad_(True)
        e_attr = data["victim", "requests", "ngo"].edge_attr.clone().detach().requires_grad_(True)

        tmp = HeteroData()
        tmp["victim"].x = v_x
        tmp["ngo"].x = n_x
        tmp["victim", "requests", "ngo"].edge_index = data["victim", "requests", "ngo"].edge_index
        tmp["victim", "requests", "ngo"].edge_attr = e_attr
        tmp["ngo", "serves", "victim"].edge_index = data["ngo", "serves", "victim"].edge_index
        tmp["ngo", "serves", "victim"].edge_attr = data["ngo", "serves", "victim"].edge_attr.clone().detach()

        logits = model(tmp)

        edge_index = tmp["victim", "requests", "ngo"].edge_index
        mask = (edge_index[0] == victim_idx) & (edge_index[1] == ngo_idx)
        edge_positions = mask.nonzero(as_tuple=True)[0]
        if len(edge_positions) == 0:
            return []

        target_logit = logits[edge_positions[0]]
        target_logit.backward()

        importances: list[tuple[str, float, float]] = []

        if v_x.grad is not None:
            v_grad = (v_x.grad[victim_idx] * v_x.data[victim_idx]).abs().cpu().numpy()
            for i, name in enumerate(victim_feature_names):
                if i < len(v_grad):
                    importances.append((f"victim.{name}", float(v_grad[i]), float(v_x.data[victim_idx, i])))

        if n_x.grad is not None:
            n_grad = (n_x.grad[ngo_idx] * n_x.data[ngo_idx]).abs().cpu().numpy()
            for i, name in enumerate(ngo_feature_names):
                if i < len(n_grad):
                    importances.append((f"ngo.{name}", float(n_grad[i]), float(n_x.data[ngo_idx, i])))

        if e_attr.grad is not None:
            e_pos = edge_positions[0].item()
            e_grad = (e_attr.grad[e_pos] * e_attr.data[e_pos]).abs().cpu().numpy()
            for i, name in enumerate(edge_feature_names):
                if i < len(e_grad):
                    importances.append((f"edge.{name}", float(e_grad[i]), float(e_attr.data[e_pos, i])))

        importances.sort(key=lambda t: t[1], reverse=True)

        return [
            {"feature": name, "importance": round(imp, 6), "value": round(val, 4)}
            for name, imp, val in importances[:top_k]
        ]

    # =====================================================================
    #  Checkpoint helpers
    # =====================================================================

    def save_checkpoint(model: nn.Module, path: Path | str | None = None) -> Path | None:
        """Save model weights to disk."""
        if not _HAS_GAT_DEPS:
            logger.error("Cannot save GAT checkpoint — dependencies missing")
            return None
        path = Path(path or DEFAULT_CHECKPOINT)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), path)
        logger.info("GAT checkpoint saved → %s", path)
        return path

    def load_checkpoint(
        path: Path | str | None = None,
        **model_kwargs: Any,
    ) -> Any:
        """Load a trained GATAllocator from disk."""
        if not _HAS_GAT_DEPS:
            logger.error("Cannot load GAT checkpoint — dependencies missing")
            return None
        path = Path(path or DEFAULT_CHECKPOINT)
        model = GATAllocator(**model_kwargs)
        if path.exists():
            model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
            model.eval()
            logger.info("GAT checkpoint loaded ← %s", path)
        else:
            logger.warning("GAT checkpoint not found at %s", path)
        return model

else:
    HeteroGATEncoder = None
    BilinearAssignmentHead = None
    GATAllocator = None

    def hungarian_assignment(*args, **kwargs):
        logger.error("Cannot run hungarian_assignment — dependencies missing")
        return []

    def explain_assignment(*args, **kwargs):
        logger.error("Cannot run explain_assignment — dependencies missing")
        return []

    def save_checkpoint(*args, **kwargs):
        logger.error("Cannot save GAT checkpoint — dependencies missing")
        return None

    def load_checkpoint(*args, **kwargs):
        logger.error("Cannot load GAT checkpoint — dependencies missing")
        return None
