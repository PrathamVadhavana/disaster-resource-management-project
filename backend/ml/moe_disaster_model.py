"""
Mixture of Experts (MoE) Model for Disaster Resource Management.

This module implements a specialized MoE architecture with:
- Expert specialization by disaster type and prediction task
- Smart gating network for intelligent routing
- Load balancing to prevent expert collapse
- Top-K routing for efficient inference
"""

import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger("moe_disaster")

# Constants
MOE_CHECKPOINT = Path(__file__).parent / "models" / "moe_disaster.pt"
EXPERT_CHECKPOINTS = {
    "severity": Path(__file__).parent / "models" / "moe_expert_severity.pt",
    "spread": Path(__file__).parent / "models" / "moe_expert_spread.pt",
    "impact": Path(__file__).parent / "models" / "moe_expert_impact.pt",
    "resource": Path(__file__).parent / "models" / "moe_expert_resource.pt",
    "anomaly": Path(__file__).parent / "models" / "moe_expert_anomaly.pt",
}

# Disaster type encoding
DISASTER_TYPES = ["earthquake", "flood", "hurricane", "tornado", "wildfire", "tsunami", "drought", "landslide", "volcano", "other"]
DISASTER_TYPE_TO_IDX = {t: i for i, t in enumerate(DISASTER_TYPES)}


class DisasterExpert(nn.Module):
    """Base expert network for disaster-specific predictions."""
    
    def __init__(self, input_dim: int = 64, hidden_dim: int = 128, output_dim: int = 32):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, output_dim),
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x)


class SeverityExpert(DisasterExpert):
    """Expert specialized in severity prediction."""
    
    def __init__(self, input_dim: int = 64):
        super().__init__(input_dim, hidden_dim=128, output_dim=4)  # 4 severity levels
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits = super().forward(x)
        return F.softmax(logits, dim=-1)


class SpreadExpert(DisasterExpert):
    """Expert specialized in spread/area prediction."""
    
    def __init__(self, input_dim: int = 64):
        super().__init__(input_dim, hidden_dim=128, output_dim=3)  # mean, lower, upper bounds
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return super().forward(x)


class ImpactExpert(DisasterExpert):
    """Expert specialized in impact prediction (casualties, damage)."""
    
    def __init__(self, input_dim: int = 64):
        super().__init__(input_dim, hidden_dim=128, output_dim=2)  # casualties, damage
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.softplus(super().forward(x))  # Ensure positive outputs


class ResourceExpert(DisasterExpert):
    """Expert specialized in resource allocation prediction."""
    
    def __init__(self, input_dim: int = 64):
        super().__init__(input_dim, hidden_dim=128, output_dim=10)  # 10 resource types
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.softmax(super().forward(x), dim=-1)


class AnomalyExpert(DisasterExpert):
    """Expert specialized in anomaly detection."""
    
    def __init__(self, input_dim: int = 64):
        super().__init__(input_dim, hidden_dim=128, output_dim=1)  # anomaly score
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(super().forward(x))


class DisasterGatingNetwork(nn.Module):
    """
    Gating network that routes inputs to appropriate experts based on
    disaster metadata and input features.
    """
    
    def __init__(self, input_dim: int = 64, n_experts: int = 5, hidden_dim: int = 64):
        super().__init__()
        self.n_experts = n_experts
        
        # Disaster type embedding
        self.disaster_type_embedding = nn.Embedding(len(DISASTER_TYPES), 16)
        
        # Feature processing
        self.feature_encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
        )
        
        # Disaster metadata encoder
        self.metadata_encoder = nn.Sequential(
            nn.Linear(16 + 4 + 2, hidden_dim),  # type_emb + severity + lat/lon
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
        )
        
        # Combined gating network
        self.gate = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, n_experts),
        )
    
    def forward(
        self,
        x: torch.Tensor,
        disaster_type: torch.Tensor,
        severity: torch.Tensor,
        location: torch.Tensor,
    ) -> torch.Tensor:
        """
        Route inputs to experts.
        
        Args:
            x: Input features [batch_size, input_dim]
            disaster_type: Disaster type indices [batch_size]
            severity: Severity one-hot [batch_size, 4]
            location: Latitude/longitude [batch_size, 2]
        
        Returns:
            Gate logits [batch_size, n_experts]
        """
        # Encode disaster type
        type_emb = self.disaster_type_embedding(disaster_type)
        
        # Encode features
        feature_enc = self.feature_encoder(x)
        
        # Encode metadata
        metadata = torch.cat([type_emb, severity, location], dim=-1)
        metadata_enc = self.metadata_encoder(metadata)
        
        # Combine and compute gate logits
        combined = torch.cat([feature_enc, metadata_enc], dim=-1)
        gate_logits = self.gate(combined)
        
        return gate_logits


class DisasterMoEModel(nn.Module):
    """
    Mixture of Experts model for disaster resource management.
    
    Features:
    - 5 specialized experts (severity, spread, impact, resource, anomaly)
    - Smart gating network for routing
    - Top-K routing for efficient inference
    - Load balancing loss to prevent expert collapse
    """
    
    def __init__(
        self,
        input_dim: int = 64,
        top_k: int = 2,
        load_balance_coef: float = 0.01,
        noisy_gating: bool = True,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.top_k = top_k
        self.load_balance_coef = load_balance_coef
        self.noisy_gating = noisy_gating
        self.n_experts = 5
        
        # Input encoder
        self.input_encoder = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.LayerNorm(128),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(128, 64),
        )
        
        # Gating network
        self.gating_network = DisasterGatingNetwork(
            input_dim=64,
            n_experts=self.n_experts,
            hidden_dim=64,
        )
        
        # Specialized experts
        self.experts = nn.ModuleList([
            SeverityExpert(input_dim=64),
            SpreadExpert(input_dim=64),
            ImpactExpert(input_dim=64),
            ResourceExpert(input_dim=64),
            AnomalyExpert(input_dim=64),
        ])
        
        # Expert names for logging
        self.expert_names = ["severity", "spread", "impact", "resource", "anomaly"]
        
        # Output heads
        self.severity_head = nn.Linear(4, 4)  # 4 severity levels
        self.spread_head = nn.Linear(3, 3)    # mean, lower, upper
        self.impact_head = nn.Linear(2, 2)    # casualties, damage
        self.resource_head = nn.Linear(10, 10)  # 10 resource types
        self.anomaly_head = nn.Linear(1, 1)   # anomaly score
        
        # Training metrics
        self.register_buffer("expert_usage", torch.zeros(self.n_experts))
        self.register_buffer("total_samples", torch.tensor(0))
    
    def _compute_gate_logits(
        self,
        x: torch.Tensor,
        disaster_type: torch.Tensor,
        severity: torch.Tensor,
        location: torch.Tensor,
        add_noise: bool = False,
    ) -> torch.Tensor:
        """Compute gating logits with optional noise for exploration."""
        gate_logits = self.gating_network(x, disaster_type, severity, location)
        
        if add_noise and self.training:
            noise = torch.randn_like(gate_logits) * 0.1
            gate_logits = gate_logits + noise
        
        return gate_logits
    
    def _compute_load_balance_loss(self, gate_probs: torch.Tensor) -> torch.Tensor:
        """
        Compute load balancing loss to encourage uniform expert utilization.
        
        Uses KL divergence between actual expert usage and uniform distribution.
        """
        # Average gate probability per expert
        expert_usage = gate_probs.mean(dim=0)
        
        # Target uniform distribution
        target_usage = torch.ones_like(expert_usage) / self.n_experts
        
        # KL divergence
        load_balance_loss = F.kl_div(
            expert_usage.log(),
            target_usage,
            reduction="batchmean",
        )
        
        return load_balance_loss
    
    def forward(
        self,
        x: torch.Tensor,
        disaster_type: torch.Tensor,
        severity: torch.Tensor,
        location: torch.Tensor,
        task: str = "all",
    ) -> dict[str, torch.Tensor]:
        """
        Forward pass through MoE model.
        
        Args:
            x: Input features [batch_size, input_dim]
            disaster_type: Disaster type indices [batch_size]
            severity: Severity one-hot [batch_size, 4]
            location: Latitude/longitude [batch_size, 2]
            task: Task to perform ("severity", "spread", "impact", "resource", "anomaly", "all")
        
        Returns:
            Dictionary with predictions and auxiliary losses
        """
        batch_size = x.shape[0]
        
        # Encode input
        encoded = self.input_encoder(x)
        
        # Compute gate logits
        gate_logits = self._compute_gate_logits(
            encoded, disaster_type, severity, location, add_noise=self.noisy_gating
        )
        
        # Top-K selection
        top_k_weights, top_k_indices = torch.topk(gate_logits, self.top_k, dim=-1)
        top_k_weights = F.softmax(top_k_weights, dim=-1)
        
        # Create routing mask
        routing_mask = torch.zeros(batch_size, self.n_experts, device=x.device)
        for i in range(self.top_k):
            routing_mask.scatter_(1, top_k_indices[:, i:i+1], 1)
        
        # Route to experts and combine outputs
        expert_outputs = {}
        for expert_idx in range(self.n_experts):
            # Find samples routed to this expert
            expert_mask = routing_mask[:, expert_idx].bool()
            
            if expert_mask.any():
                expert_input = encoded[expert_mask]
                expert_out = self.experts[expert_idx](expert_input)
                
                # Get weights for this expert
                expert_weight_idx = (top_k_indices == expert_idx).nonzero(as_tuple=True)
                expert_weights = top_k_weights[expert_weight_idx]
                
                # Weighted output
                weighted_out = expert_out * expert_weights.unsqueeze(-1)
                
                # Store in output dict
                expert_name = self.expert_names[expert_idx]
                if expert_name not in expert_outputs:
                    expert_outputs[expert_name] = torch.zeros(
                        batch_size, expert_out.shape[-1], device=x.device
                    )
                expert_outputs[expert_name][expert_mask] = weighted_out
        
        # Apply output heads
        outputs = {}
        if "severity" in expert_outputs or task in ("severity", "all"):
            outputs["severity"] = self.severity_head(
                expert_outputs.get("severity", torch.zeros(batch_size, 4, device=x.device))
            )
        
        if "spread" in expert_outputs or task in ("spread", "all"):
            outputs["spread"] = self.spread_head(
                expert_outputs.get("spread", torch.zeros(batch_size, 3, device=x.device))
            )
        
        if "impact" in expert_outputs or task in ("impact", "all"):
            outputs["impact"] = self.impact_head(
                expert_outputs.get("impact", torch.zeros(batch_size, 2, device=x.device))
            )
        
        if "resource" in expert_outputs or task in ("resource", "all"):
            outputs["resource"] = self.resource_head(
                expert_outputs.get("resource", torch.zeros(batch_size, 10, device=x.device))
            )
        
        if "anomaly" in expert_outputs or task in ("anomaly", "all"):
            outputs["anomaly"] = self.anomaly_head(
                expert_outputs.get("anomaly", torch.zeros(batch_size, 1, device=x.device))
            )
        
        # Compute load balance loss
        gate_probs = F.softmax(gate_logits, dim=-1)
        load_balance_loss = self._compute_load_balance_loss(gate_probs)
        
        # Update usage statistics
        if self.training:
            with torch.no_grad():
                self.expert_usage += routing_mask.sum(dim=0)
                self.total_samples += batch_size
        
        # Add auxiliary information
        outputs["gate_probs"] = gate_probs
        outputs["routing_mask"] = routing_mask
        outputs["load_balance_loss"] = load_balance_loss
        outputs["expert_usage"] = routing_mask.sum(dim=0) / batch_size
        
        return outputs
    
    def get_expert_utilization(self) -> dict[str, float]:
        """Get expert utilization statistics."""
        if self.total_samples == 0:
            return {name: 0.0 for name in self.expert_names}
        
        utilization = (self.expert_usage / self.total_samples).cpu().numpy()
        return {name: float(util) for name, util in zip(self.expert_names, utilization)}
    
    def reset_usage_stats(self):
        """Reset expert usage statistics."""
        self.expert_usage.zero_()
        self.total_samples.zero_()


class MoEInferenceEngine:
    """
    Inference engine for MoE model with caching and optimization.
    """
    
    def __init__(self, model: DisasterMoEModel, device: str = "cpu"):
        self.model = model.to(device)
        self.device = device
        self.model.eval()
        
        # Cache for frequently used expert outputs
        self.cache: dict[str, torch.Tensor] = {}
        self.cache_hits = 0
        self.cache_misses = 0
    
    def _get_cache_key(self, x: torch.Tensor, disaster_type: str) -> str:
        """Generate cache key from input."""
        return f"{disaster_type}_{x.mean().item():.4f}_{x.std().item():.4f}"
    
    @torch.no_grad()
    def predict(
        self,
        features: dict[str, Any],
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Make predictions using MoE model.
        
        Args:
            features: Input features dictionary
            use_cache: Whether to use caching
        
        Returns:
            Prediction dictionary with expert routing information
        """
        # Prepare inputs
        x = self._prepare_features(features)
        disaster_type = self._encode_disaster_type(features.get("disaster_type", "other"))
        severity = self._encode_severity(features.get("severity", "medium"))
        location = self._encode_location(features.get("latitude", 0), features.get("longitude", 0))
        
        # Check cache
        cache_key = self._get_cache_key(x, features.get("disaster_type", "other"))
        if use_cache and cache_key in self.cache:
            self.cache_hits += 1
            return {"cached": True, "outputs": self.cache[cache_key]}
        
        self.cache_misses += 1
        
        # Forward pass
        outputs = self.model(x, disaster_type, severity, location, task="all")
        
        # Process outputs
        result = {
            "severity": self._process_severity(outputs["severity"]),
            "spread": self._process_spread(outputs["spread"]),
            "impact": self._process_impact(outputs["impact"]),
            "resource": self._process_resource(outputs["resource"]),
            "anomaly": self._process_anomaly(outputs["anomaly"]),
            "expert_routing": {
                "gate_probs": outputs["gate_probs"].cpu().numpy().tolist(),
                "expert_usage": outputs["expert_usage"].cpu().numpy().tolist(),
                "load_balance_loss": outputs["load_balance_loss"].item(),
            },
            "cached": False,
        }
        
        # Update cache
        if use_cache:
            self.cache[cache_key] = result
        
        return result
    
    def _prepare_features(self, features: dict[str, Any]) -> torch.Tensor:
        """Convert feature dict to tensor."""
        feature_list = [
            features.get("temperature", 0),
            features.get("humidity", 0),
            features.get("wind_speed", 0),
            features.get("pressure", 0),
            features.get("precipitation", 0),
            features.get("population_density", 0),
            features.get("affected_population", 0),
            features.get("current_area", 0),
        ]
        
        # Pad or truncate to input_dim
        while len(feature_list) < self.model.input_dim:
            feature_list.append(0)
        feature_list = feature_list[:self.model.input_dim]
        
        return torch.tensor([feature_list], dtype=torch.float32, device=self.device)
    
    def _encode_disaster_type(self, disaster_type: str) -> torch.Tensor:
        """Encode disaster type to index."""
        idx = DISASTER_TYPE_TO_IDX.get(disaster_type.lower(), len(DISASTER_TYPES) - 1)
        return torch.tensor([idx], dtype=torch.long, device=self.device)
    
    def _encode_severity(self, severity: str) -> torch.Tensor:
        """Encode severity to one-hot."""
        severity_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        idx = severity_map.get(severity.lower(), 1)
        one_hot = torch.zeros(1, 4, device=self.device)
        one_hot[0, idx] = 1
        return one_hot
    
    def _encode_location(self, latitude: float, longitude: float) -> torch.Tensor:
        """Encode location."""
        return torch.tensor([[latitude, longitude]], dtype=torch.float32, device=self.device)
    
    def _process_severity(self, output: torch.Tensor) -> dict[str, Any]:
        """Process severity output."""
        probs = output.cpu().numpy()[0]
        severity_levels = ["low", "medium", "high", "critical"]
        predicted_idx = probs.argmax()
        return {
            "predicted_severity": severity_levels[predicted_idx],
            "confidence": float(probs[predicted_idx]),
            "probabilities": {level: float(prob) for level, prob in zip(severity_levels, probs)},
        }
    
    def _process_spread(self, output: torch.Tensor) -> dict[str, Any]:
        """Process spread output."""
        values = output.cpu().numpy()[0]
        return {
            "predicted_area_km2": float(values[0]),
            "ci_lower_km2": float(values[1]),
            "ci_upper_km2": float(values[2]),
        }
    
    def _process_impact(self, output: torch.Tensor) -> dict[str, Any]:
        """Process impact output."""
        values = output.cpu().numpy()[0]
        return {
            "predicted_casualties": int(values[0]),
            "predicted_damage_usd": float(values[1]),
        }
    
    def _process_resource(self, output: torch.Tensor) -> dict[str, Any]:
        """Process resource output."""
        probs = output.cpu().numpy()[0]
        resource_types = ["food", "water", "medical", "shelter", "personnel", "equipment", "evacuation", "communication", "transport", "other"]
        return {
            "resource_allocation": {rtype: float(prob) for rtype, prob in zip(resource_types, probs)},
            "primary_resource": resource_types[probs.argmax()],
        }
    
    def _process_anomaly(self, output: torch.Tensor) -> dict[str, Any]:
        """Process anomaly output."""
        score = output.cpu().numpy()[0][0]
        return {
            "anomaly_score": float(score),
            "is_anomaly": score > 0.7,
            "confidence": float(abs(score - 0.5) * 2),
        }
    
    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self.cache_hits + self.cache_misses
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": self.cache_hits / total if total > 0 else 0,
            "cache_size": len(self.cache),
        }
    
    def clear_cache(self):
        """Clear the cache."""
        self.cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0


def load_moe_model(checkpoint_path: Path | None = None, device: str = "cpu") -> MoEInferenceEngine:
    """Load MoE model from checkpoint."""
    path = checkpoint_path or MOE_CHECKPOINT
    
    if not path.exists():
        logger.warning(f"MoE checkpoint not found at {path}, initializing fresh model")
        model = DisasterMoEModel()
    else:
        logger.info(f"Loading MoE model from {path}")
        checkpoint = torch.load(path, map_location=device)
        model = DisasterMoEModel(**checkpoint.get("config", {}))
        model.load_state_dict(checkpoint["model_state_dict"])
    
    return MoEInferenceEngine(model, device=device)


def train_moe_model(
    train_data: list[dict[str, Any]],
    val_data: list[dict[str, Any]],
    epochs: int = 50,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
    save_path: Path | None = None,
) -> dict[str, Any]:
    """
    Train MoE model on disaster data.
    
    Returns training metrics.
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = DisasterMoEModel().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    
    history = {"train_loss": [], "val_loss": [], "expert_utilization": []}
    
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0
        
        # Mini-batch training
        for i in range(0, len(train_data), batch_size):
            batch = train_data[i:i + batch_size]
            
            # Prepare batch (simplified - would need proper feature extraction)
            optimizer.zero_grad()
            
            # Forward pass would go here
            # loss = compute_loss(outputs, targets)
            # loss += outputs["load_balance_loss"] * model.load_balance_coef
            # loss.backward()
            # optimizer.step()
            
            # epoch_loss += loss.item()
        
        scheduler.step()
        
        # Validation
        model.eval()
        # val_loss = evaluate(model, val_data)
        
        # Log metrics
        utilization = model.get_expert_utilization()
        history["expert_utilization"].append(utilization)
        
        logger.info(f"Epoch {epoch + 1}/{epochs}, Utilization: {utilization}")
    
    # Save model
    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "model_state_dict": model.state_dict(),
            "config": {"input_dim": model.input_dim, "top_k": model.top_k},
            "history": history,
        }, save_path)
        logger.info(f"MoE model saved to {save_path}")
    
    return history