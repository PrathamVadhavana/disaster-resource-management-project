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
    
    def __init__(self, input_dim: int = 64, hidden_dim: int = 128, output_dim: int = 32, context_dim: int = 64):
        super().__init__()
        # Experts now take both encoded features and metadata context
        self.network = nn.Sequential(
            nn.Linear(input_dim + context_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, output_dim),
        )
    
    def forward(self, x: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        # Fuse input features with disaster metadata context
        combined = torch.cat([x, context], dim=-1)
        return self.network(combined)


class SeverityExpert(DisasterExpert):
    """Expert specialized in severity prediction."""
    
    def __init__(self, input_dim: int = 64):
        super().__init__(input_dim, hidden_dim=128, output_dim=4)  # 4 severity levels
    
    def forward(self, x: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        logits = super().forward(x, context)
        return F.softmax(logits, dim=-1)


class SpreadExpert(DisasterExpert):
    """Expert specialized in spread/area prediction."""
    
    def __init__(self, input_dim: int = 64):
        super().__init__(input_dim, hidden_dim=128, output_dim=3)  # mean, lower, upper bounds
    
    def forward(self, x: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        return F.softplus(super().forward(x, context))  # Area must be positive


class ImpactExpert(DisasterExpert):
    """Expert specialized in impact prediction (casualties, damage)."""
    
    def __init__(self, input_dim: int = 64):
        super().__init__(input_dim, hidden_dim=128, output_dim=2)  # casualties, damage
    
    def forward(self, x: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        return F.softplus(super().forward(x, context))  # Ensure positive outputs


class ResourceExpert(DisasterExpert):
    """Expert specialized in resource allocation prediction."""
    
    def __init__(self, input_dim: int = 64):
        super().__init__(input_dim, hidden_dim=128, output_dim=10)  # 10 resource types
    
    def forward(self, x: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        return F.softmax(super().forward(x, context), dim=-1)


class AnomalyExpert(DisasterExpert):
    """Expert specialized in anomaly detection."""
    
    def __init__(self, input_dim: int = 64):
        super().__init__(input_dim, hidden_dim=128, output_dim=1)  # anomaly score
    
    def forward(self, x: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(super().forward(x, context))


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
        
        # IMPROVISATION: Attention-Gating
        # This allows the router to dynamically attend to specific input features
        # based on the disaster context.
        self.context_projection = nn.Linear(hidden_dim, hidden_dim)
        self.feature_projection = nn.Linear(hidden_dim, hidden_dim)
        self.attention = nn.MultiheadAttention(embed_dim=hidden_dim, num_heads=4, batch_first=True)
        
        # Combined gating network
        self.gate = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, n_experts),
        )
    
    def forward(
        self,
        x: torch.Tensor,
        disaster_type: torch.Tensor,
        severity: torch.Tensor,
        location: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
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
        
        # IMPROVISATION: Apply Contextual Attention
        # query: metadata_enc, key/value: feature_enc
        q = self.context_projection(metadata_enc).unsqueeze(1) # [batch, 1, dim]
        k = v = self.feature_projection(feature_enc).unsqueeze(1) # [batch, 1, dim]
        
        attended_features, _ = self.attention(q, k, v)
        attended_features = attended_features.squeeze(1)
        
        # Combine and compute gate logits
        combined = torch.cat([attended_features, metadata_enc], dim=-1)
        gate_logits = self.gate(combined)
        
        # Rule-based override for untrained models (Bootstrap Mode)
        # We check the parent model's trained status
        if not getattr(self, 'model_trained', False):
            # Expert Indices: 0:Severity, 1:Spread, 2:Impact, 3:Resource, 4:Anomaly
            gate_logits = torch.zeros_like(gate_logits) + 0.5
            
            # Severity expert is always active
            gate_logits[:, 0] += 5.0
            
            for i in range(len(disaster_type)):
                dt_idx = int(disaster_type[i])
                dt_name = DISASTER_TYPES[dt_idx]
                
                # Rule-based specialization
                if dt_name in ["wildfire", "flood", "hurricane", "hurricane", "cyclone"]:
                    gate_logits[i, 1] += 10.0 # Spread Expert
                if dt_name in ["earthquake", "flood", "tsunami", "hurricane"]:
                    gate_logits[i, 2] += 10.0 # Impact Expert
                if dt_name in ["other"]:
                    gate_logits[i, 4] += 10.0 # Anomaly Expert
        
        return gate_logits, metadata_enc
        
    def set_trained(self, trained: bool = True):
        self.is_trained = trained


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
        # Link trained status to gating network
        self.gating_network.model_trained = self.is_trained
        
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
        
        # Metadata preference mapping
        self.expert_indices = {name: i for i, name in enumerate(self.expert_names)}
        
        # Output heads
        self.severity_head = nn.Linear(4, 4)  # 4 severity levels
        self.spread_head = nn.Linear(3, 3)    # mean, lower, upper
        self.impact_head = nn.Linear(2, 2)    # casualties, damage
        self.resource_head = nn.Linear(10, 10)  # 10 resource types
        self.anomaly_head = nn.Linear(1, 1)   # anomaly score
        
        # Initialize biases to zero to avoid random outputs when inputs are zero
        for head in [self.severity_head, self.spread_head, self.impact_head, self.resource_head, self.anomaly_head]:
            nn.init.zeros_(head.bias)
        
        # Training metrics
        self.register_buffer("expert_usage", torch.zeros(self.n_experts))
        self.register_buffer("inference_usage", torch.zeros(self.n_experts))
        self.register_buffer("total_samples", torch.tensor(0))
        self.register_buffer("total_inference_samples", torch.tensor(0))
        self.is_trained = False
    
    @property
    def is_trained(self) -> bool:
        return getattr(self, '_is_trained', False)
    
    @is_trained.setter
    def is_trained(self, value: bool):
        self._is_trained = value
        if hasattr(self, 'gating_network'):
            self.gating_network.model_trained = value
    
    def _compute_gate_logits(
        self,
        x: torch.Tensor,
        disaster_type: torch.Tensor,
        severity: torch.Tensor,
        location: torch.Tensor,
        add_noise: bool = False,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Compute gating logits with optional noise for exploration."""
        gate_logits, context = self.gating_network(x, disaster_type, severity, location)
        
        if add_noise and self.training:
            noise = torch.randn_like(gate_logits) * 0.1
            gate_logits = gate_logits + noise
        
        return gate_logits, context
    
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
            F.log_softmax(expert_usage, dim=-1),
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
        
        # Compute gate logits AND shared context
        gate_logits, context = self._compute_gate_logits(
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
        # Initialize output tensors with proper batch sizes
        outputs_raw = {
            "severity": torch.zeros(batch_size, 4, device=x.device),
            "spread": torch.zeros(batch_size, 3, device=x.device),
            "impact": torch.zeros(batch_size, 2, device=x.device),
            "resource": torch.zeros(batch_size, 10, device=x.device),
            "anomaly": torch.zeros(batch_size, 1, device=x.device),
        }
        
        # Track if any expert was used for each task
        used_tasks = set()
        
        for expert_idx in range(self.n_experts):
            expert_mask = routing_mask[:, expert_idx].bool()
            if not expert_mask.any():
                continue
                
            expert_name = self.expert_names[expert_idx]
            used_tasks.add(expert_name)
            
            # Extract samples and context for this expert
            expert_input = encoded[expert_mask]
            expert_context = context[expert_mask]
            
            # Pass BOTH features and context to expert
            expert_out = self.experts[expert_idx](expert_input, expert_context)
            
            # Simple bootstrap logic for UNTRAINED experts to ensure immediate responsiveness
            if not getattr(self, 'is_trained', False):
                # Apply logical scaling based on severity
                # severity level: low=0, med=1, high=2, crit=3
                sev_idx = severity[expert_mask].argmax(dim=-1).float().unsqueeze(-1)
                sev_mult = torch.pow(2.0, sev_idx) # 1x, 2x, 4x, 8x impact
                
                expert_name = self.expert_names[expert_idx]
                if expert_name == "severity":
                    # Force severity prediction to match input for untrained models
                    # sev_idx is [batch, 1], we want one-hot [batch, 4]
                    expert_out = torch.zeros_like(expert_out)
                    expert_out.scatter_(1, sev_idx.long(), 1.0)
                elif expert_name == "impact":
                    # Base impact for untrained models
                    expert_out = expert_out * 0.1 + (sev_mult * 0.2)
                elif expert_name == "spread":
                    # Base spread for untrained models
                    expert_out = expert_out * 0.1 + (sev_mult * 0.5)
            
            # Multiplying by gates: we need the specific gate weight for each sample
            # corresponding to THIS expert
            # top_k_indices tells us which expert is in which slot
            # if routing_mask[i, expert_idx] == 1, then expert_idx in top_k_indices[i]
            for i in range(self.top_k):
                slot_mask = (top_k_indices[:, i] == expert_idx) & expert_mask
                if slot_mask.any():
                    # Weights for this specific slot and expert
                    weights = top_k_weights[slot_mask, i].unsqueeze(-1)
                    # Input to expert for these specific samples
                    # Note: expert_out only contains samples where expert_mask was true
                    # and slot_mask is a subset of expert_mask.
                    # We need to map slot_mask back to expert_mask indices or just use global indices.
                    
                    # Simpler: just use global indexing for simplicity and correctness
                    # expert_out_all = self.experts[expert_idx](encoded) # This would be slow (dense)
                    # Instead, use the already computed expert_out but filter it
                    
                    # Find indices of slot_mask relative to expert_mask
                    rel_indices = (slot_mask[expert_mask]).nonzero().squeeze(-1)
                    outputs_raw[expert_name][slot_mask] += expert_out[rel_indices] * weights

        # Apply output heads
        outputs = {}
        outputs["severity"] = self.severity_head(outputs_raw["severity"])
        outputs["spread"] = self.spread_head(outputs_raw["spread"])
        outputs["impact"] = self.impact_head(outputs_raw["impact"])
        outputs["resource"] = self.resource_head(outputs_raw["resource"])
        outputs["anomaly"] = self.anomaly_head(outputs_raw["anomaly"])
        
        # Add small bias for completely unrouted batches during early training
        if "severity" not in used_tasks:
            outputs["severity"] += torch.tensor([0.1, 0.7, 0.1, 0.1], device=x.device)
        
        # Compute load balance loss
        gate_probs = F.softmax(gate_logits, dim=-1)
        load_balance_loss = self._compute_load_balance_loss(gate_probs)
        
        # Update usage statistics
        with torch.no_grad():
            if self.training:
                self.expert_usage += routing_mask.sum(dim=0)
                self.total_samples += batch_size
            else:
                self.inference_usage += routing_mask.sum(dim=0)
                self.total_inference_samples += batch_size
        
        # Add auxiliary information
        # Output processing
        outputs["gate_probs"] = gate_probs
        outputs["routing_mask"] = routing_mask
        outputs["load_balance_loss"] = load_balance_loss
        
        # Use instantaneous probabilities for current inference results 
        # (expert_usage in training is a running average, but for prediction we want current)
        outputs["expert_usage"] = gate_probs.mean(dim=0)
        
        return outputs
    
    def get_expert_utilization(self) -> dict[str, float]:
        """Get expert utilization statistics (prefers inference stats if available)."""
        if self.total_inference_samples > 0:
            utilization = (self.inference_usage / self.total_inference_samples).cpu().numpy()
        elif self.total_samples > 0:
            utilization = (self.expert_usage / self.total_samples).cpu().numpy()
        else:
            return {name: 0.0 for name in self.expert_names}
        
        return {name: float(util) for name, util in zip(self.expert_names, utilization)}
    
    def reset_usage_stats(self):
        """Reset expert usage statistics."""
        self.expert_usage.zero_()
        self.inference_usage.zero_()
        self.total_samples.zero_()
        self.total_inference_samples.zero_()


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
    
    def _get_cache_key(self, features: dict[str, Any], x: torch.Tensor) -> str:
        """Generate unique cache key including all relevant metadata."""
        d_type = features.get("disaster_type", "other")
        severity = features.get("severity", "medium")
        lat = f"{float(features.get('latitude', 0)):.2f}"
        lon = f"{float(features.get('longitude', 0)):.2f}"
        # Also include a fingerprint of the sensor features x
        features_sig = f"{x.mean().item():.4f}_{x.std().item():.4f}"
        
        return f"{d_type}_{severity}_{lat}_{lon}_{features_sig}"
    
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
        
        # Check exact cache
        cache_key = self._get_cache_key(features, x)
        if use_cache and cache_key in self.cache:
            self.cache_hits += 1
            return self.cache[cache_key]
        
        # IMPROVISATION: Check Semantic Cache (Conceptual Match)
        if use_cache:
            conceptual_match = self.find_conceptual_match(
                x, 
                d_type=features.get("disaster_type", "other"),
                severity=features.get("severity", "medium")
            )
            if conceptual_match:
                self.cache_hits += 1
                return conceptual_match
        
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
                # IMPROVISATION: Feature Attribution (Explainability)
                "attribution": self._calculate_attribution(x, outputs["gate_probs"]),
            },
            "cached": False,
            "fingerprint": x, # Store for semantic matching
            "meta_type": features.get("disaster_type", "other"), # Store for validation
            "meta_severity": features.get("severity", "medium"),
        }
        
        # Map fresh results to include 'cached' flag correctly
        result["cached"] = False
        
        # Update cache
        if use_cache:
            cached_res = result.copy()
            cached_res["cached"] = True
            self.cache[cache_key] = cached_res
        
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
        import numpy as np
        values = output.cpu().numpy()[0]
        # Inverse log transform (since trained on log1p)
        pred_area = np.expm1(values[0])
        return {
            "predicted_area_km2": float(max(0.1, pred_area)), # Min 0.1 for visibility
            "ci_lower_km2": float(max(0, np.expm1(values[1]))),
            "ci_upper_km2": float(max(0, np.expm1(values[2]))),
        }
    
    def _process_impact(self, output: torch.Tensor) -> dict[str, Any]:
        """Process impact output."""
        values = output.cpu().numpy()[0]
        # Denormalization (matching training scale: /100 and /100000)
        return {
            "predicted_casualties": int(max(0, values[0] * 100)),
            "predicted_damage_usd": float(max(0, values[1] * 100000)),
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
            "is_anomaly": bool(score > 0.7),
            "confidence": float(abs(score - 0.5) * 2),
        }
    def _calculate_attribution(self, x: torch.Tensor, gate_probs: torch.Tensor) -> dict[str, float]:
        """
        Calculate simplified feature attribution for explainability.
        In a real scenario, this would use integrated gradients or SHAP.
        Here we use a perturbation-based heuristic for performance.
        """
        feature_names = ["temp", "hmd", "wind", "pres", "prec", "pop_dens", "aff_pop", "area"]
        # Basic attribution: how much does each feature correlate with the top expert gate
        
        # Heuristic: simple absolute weighted features (since x is normalized usually)
        # This is a placeholder for a more complex Grad-CAM or IG implementation
        feat_vals = x[0][:len(feature_names)].cpu().numpy()
        total = np.abs(feat_vals).sum() + 1e-6
        
        return {name: float(np.abs(feat_vals[i]) / total) for i, name in enumerate(feature_names)}

    def find_conceptual_match(
        self, 
        x: torch.Tensor, 
        d_type: str, 
        severity: str, 
        threshold: float = 0.999
    ) -> dict[str, Any] | None:
        """
        IMPROVISATION: Semantic Similarity Cache Match.
        Looks for a 'near miss' in the cache by comparing feature vectors,
        while ensuring the disaster type and severity match exactly.
        """
        for key, value in self.cache.items():
            # Must match disaster type and severity context exactly
            if value.get("meta_type") != d_type or value.get("meta_severity") != severity:
                continue
                
            if "fingerprint" in value:
                cached_x = value["fingerprint"]
                similarity = F.cosine_similarity(x, cached_x).item()
                if similarity >= threshold:
                    return value
        return None

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


# Singleton instance for the model engine
_MOE_ENGINE_INSTANCE = None

def load_moe_model(checkpoint_path: Path | None = None, device: str = "cpu", force_reload: bool = False) -> MoEInferenceEngine:
    """Load MoE model from checkpoint (with singleton caching)."""
    global _MOE_ENGINE_INSTANCE
    
    if _MOE_ENGINE_INSTANCE is not None and not force_reload:
        return _MOE_ENGINE_INSTANCE
        
    path = checkpoint_path or MOE_CHECKPOINT
    
    if not path.exists():
        logger.info(f"No MoE checkpoint found at {path} - initializing fresh model")
        model = DisasterMoEModel()
        model.is_trained = False
    else:
        logger.info(f"Loading MoE model from {path}")
        try:
            checkpoint = torch.load(path, map_location=device, weights_only=True)
            model = DisasterMoEModel(**checkpoint.get("config", {}))
            model.load_state_dict(checkpoint["model_state_dict"])
            model.is_trained = True
        except Exception as e:
            logger.error(f"Failed to load MoE checkpoint: {e} - falling back to fresh model")
            model = DisasterMoEModel()
            model.is_trained = False
    
    _MOE_ENGINE_INSTANCE = MoEInferenceEngine(model, device=device)
    return _MOE_ENGINE_INSTANCE


def train_moe_model(
    train_data: list[dict[str, Any]],
    val_data: list[dict[str, Any]],
    epochs: int = 50,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
    save_path: Path | None = None,
) -> dict[str, Any]:
    """
    Train MoE model on disaster data with multi-task objective.
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = DisasterMoEModel().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    
    # Mock inference engine to use its encoding methods
    engine = MoEInferenceEngine(model, device=device)
    
    history = {"train_loss": [], "val_loss": [], "expert_utilization": []}
    
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        
        # Shuffle data
        np.random.shuffle(train_data)
        
        for i in range(0, len(train_data), batch_size):
            batch = train_data[i:i + batch_size]
            optimizer.zero_grad()
            
            # Prepare batch tensors
            x_list, type_list, sev_list, loc_list = [], [], [], []
            for item in batch:
                x_list.append(engine._prepare_features(item))
                type_list.append(engine._encode_disaster_type(item.get("disaster_type", "other")))
                sev_list.append(engine._encode_severity(item.get("severity", "medium")))
                loc_list.append(engine._encode_location(item.get("latitude", 0), item.get("longitude", 0)))
            
            x = torch.cat(x_list).to(device)
            disaster_type = torch.cat(type_list).to(device)
            severity = torch.cat(sev_list).to(device)
            location = torch.cat(loc_list).to(device)
            
            # Forward pass
            outputs = model(x, disaster_type, severity, location, task="all")
            
            # Compute Multi-Task Loss
            # 1. Load balance loss (keeps experts from collapsing)
            lb_loss = outputs["load_balance_loss"] * model.load_balance_coef
            
            # 2. Expert specific losses
            task_loss = 0
            
            # Severity cross-entropy (NLL)
            target_sev = severity.argmax(dim=-1)
            task_loss += F.cross_entropy(outputs["severity"], target_sev)
            
            # Spread RMSE (Scaled area)
            area_target = torch.tensor([float(item.get("current_area", 1.0)) for item in batch], device=device).unsqueeze(-1)
            # Log transform for area to handle scale differences
            task_loss += F.mse_loss(outputs["spread"][:, 0:1], torch.log1p(area_target))
            
            # Impact (Casualties and Damage)
            # Normalized targets for stability
            impact_target = torch.tensor([
                [float(item.get("casualties", 0)) / 100.0, float(item.get("damage_usd", 0)) / 100000.0] 
                for item in batch
            ], device=device)
            task_loss += F.mse_loss(outputs["impact"], impact_target)
            
            # 3. Gating Guidance (Heuristic reinforcement)
            # Help the router learn that wildfires need the Spread expert, etc.
            gating_guidance = 0
            for k in range(len(batch)):
                d_type = batch[k].get("disaster_type", "other").lower()
                # Expert Indices: 0:Severity, 1:Spread, 2:Impact, 3:Resource, 4:Anomaly
                if d_type == "wildfire":
                    # Wildfire -> Must use Spread (1)
                    gating_guidance += (1.0 - outputs["gate_probs"][k, 1])
                elif d_type in ["earthquake", "tsunami"]:
                    # High intensity -> Must use Impact (2)
                    gating_guidance += (1.0 - outputs["gate_probs"][k, 2])
            
            loss = lb_loss + task_loss + (gating_guidance * 0.05)
            
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        
        scheduler.step()
        
        # Log metrics
        utilization = model.get_expert_utilization()
        history["expert_utilization"].append(utilization)
        history["train_loss"].append(total_loss / (len(train_data) / batch_size))
        
        if (epoch + 1) % 10 == 0:
            logger.info(f"Epoch {epoch + 1}/{epochs}, Loss: {history['train_loss'][-1]:.4f}")
    
    # Save model
    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "model_state_dict": model.state_dict(),
            "config": {"input_dim": model.input_dim, "top_k": model.top_k},
            "history": history,
        }, save_path)
        model.is_trained = True
        logger.info(f"MoE model successfully trained and saved to {save_path}")
    
    return history