"""
Physics-Informed Neural Network (PINN) for Disaster Spread Prediction.

Implements a true PINN that encodes physics-based loss terms derived from
the advection-diffusion PDE to predict disaster spread (fire, flood, etc.).

PDE Model
─────────
The underlying physics model is a 2D advection-diffusion equation:

    ∂u/∂t + vx·∂u/∂x + vy·∂u/∂y = D·(∂²u/∂x² + ∂²u/∂y²) + S(x, y, t)

where:
    u(x, y, t) = disaster intensity (e.g. fire temperature, flood depth)
    vx, vy     = advection velocity (wind for fire, current for flood)
    D          = diffusion coefficient (terrain-dependent)
    S          = source term (ignition points, rainfall)

The PINN learns u(x, y, t) by minimising:
    L_total = L_data + λ_pde · L_pde + λ_bc · L_bc + λ_ic · L_ic

Components:
    L_data = MSE on observed spread data
    L_pde  = PDE residual (physics constraint)
    L_bc   = boundary condition loss
    L_ic   = initial condition loss

Architecture:
    Modified MLP with Fourier feature embedding for (x, y, t) inputs.

Usage::

    pinn = PINNSpreadModel()
    pinn.train(observations, wind_data, terrain_data)
    forecast = pinn.predict(grid_points, future_timesteps)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False
    logger.warning("PyTorch not available — PINN spread model disabled")

_MODEL_DIR = Path(__file__).resolve().parent / "models"
PINN_CHECKPOINT = _MODEL_DIR / "pinn_spread.pt"


# ── Fourier Feature Embedding ────────────────────────────────────────────────

if _HAS_TORCH:
    class FourierFeatures(nn.Module):
        """Random Fourier feature embedding for positional encoding.

        Maps (x, y, t) → high-dimensional features via:
            γ(v) = [cos(2π·B·v), sin(2π·B·v)]
        where B is a fixed random matrix.

        This helps the network learn high-frequency spatial patterns
        that standard MLPs struggle with.
        """

        def __init__(self, input_dim: int = 3, n_features: int = 128, scale: float = 10.0):
            super().__init__()
            B = torch.randn(input_dim, n_features) * scale
            self.register_buffer("B", B)
            self.output_dim = n_features * 2

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            proj = 2 * math.pi * x @ self.B
            return torch.cat([torch.cos(proj), torch.sin(proj)], dim=-1)


    class PINNNetwork(nn.Module):
        """Physics-Informed Neural Network for disaster spread.

        Input:  (x, y, t) → Fourier features → MLP → u(x,y,t)

        The network predicts the disaster intensity field u(x, y, t)
        and its derivatives are computed via automatic differentiation
        to form the PDE residual loss.
        """

        def __init__(
            self,
            n_fourier: int = 128,
            hidden_dim: int = 256,
            n_layers: int = 6,
            fourier_scale: float = 10.0,
        ):
            super().__init__()
            self.fourier = FourierFeatures(input_dim=3, n_features=n_fourier, scale=fourier_scale)

            layers = []
            in_dim = self.fourier.output_dim
            for i in range(n_layers):
                out_dim = hidden_dim
                layers.append(nn.Linear(in_dim, out_dim))
                layers.append(nn.Tanh())  # Tanh for smooth derivatives
                in_dim = out_dim
            layers.append(nn.Linear(hidden_dim, 1))  # scalar output: u(x,y,t)

            self.net = nn.Sequential(*layers)

            # Learnable physics parameters
            self.log_diffusion = nn.Parameter(torch.tensor(0.0))  # log(D)
            self.vx = nn.Parameter(torch.tensor(0.0))  # advection x
            self.vy = nn.Parameter(torch.tensor(0.0))  # advection y

        @property
        def diffusion(self) -> torch.Tensor:
            return torch.exp(self.log_diffusion)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """Forward pass: (x, y, t) → u(x, y, t)."""
            features = self.fourier(x)
            return self.net(features)

else:
    FourierFeatures = None  # type: ignore[assignment,misc]
    PINNNetwork = None  # type: ignore[assignment,misc]


# ── PDE Residual Computation ─────────────────────────────────────────────────

def compute_pde_residual(
    model: Any,
    collocation_points: Any,
) -> Any:
    """Compute the advection-diffusion PDE residual at collocation points.

    PDE: ∂u/∂t + vx·∂u/∂x + vy·∂u/∂y - D·(∂²u/∂x² + ∂²u/∂y²) = 0

    All derivatives computed via torch.autograd.

    Args:
        model: PINNNetwork instance
        collocation_points: tensor of shape (N, 3) with columns (x, y, t)

    Returns:
        PDE residual tensor of shape (N, 1)
    """
    if not _HAS_TORCH:
        raise RuntimeError("PyTorch required")

    pts = collocation_points.clone().requires_grad_(True)
    u = model(pts)

    # First-order derivatives via autograd
    grad_u = torch.autograd.grad(
        u, pts,
        grad_outputs=torch.ones_like(u),
        create_graph=True,
        retain_graph=True,
    )[0]

    u_x = grad_u[:, 0:1]  # ∂u/∂x
    u_y = grad_u[:, 1:2]  # ∂u/∂y
    u_t = grad_u[:, 2:3]  # ∂u/∂t

    # Second-order derivatives
    u_xx = torch.autograd.grad(
        u_x, pts,
        grad_outputs=torch.ones_like(u_x),
        create_graph=True,
        retain_graph=True,
    )[0][:, 0:1]

    u_yy = torch.autograd.grad(
        u_y, pts,
        grad_outputs=torch.ones_like(u_y),
        create_graph=True,
        retain_graph=True,
    )[0][:, 1:2]

    # PDE residual: ∂u/∂t + vx·∂u/∂x + vy·∂u/∂y - D·(∂²u/∂x² + ∂²u/∂y²)
    D = model.diffusion
    vx = model.vx
    vy = model.vy

    residual = u_t + vx * u_x + vy * u_y - D * (u_xx + u_yy)
    return residual


# ── Training Data Structures ─────────────────────────────────────────────────

@dataclass
class SpreadObservation:
    """A single observation of disaster spread intensity."""
    x: float  # longitude or grid x
    y: float  # latitude or grid y
    t: float  # time (hours since event start)
    intensity: float  # observed intensity (0-1)


@dataclass
class TerrainParams:
    """Terrain-dependent parameters for the PDE."""
    diffusion_base: float = 0.01  # base diffusion coefficient
    wind_speed_x: float = 0.0  # m/s
    wind_speed_y: float = 0.0  # m/s
    terrain_factor: float = 1.0  # multiplier for terrain roughness


# ── PINN Spread Model ────────────────────────────────────────────────────────

class PINNSpreadModel:
    """Physics-Informed Neural Network for disaster spread prediction.

    Combines data-driven learning with physics constraints from the
    advection-diffusion PDE to produce physically-consistent forecasts
    that generalise beyond the training distribution.
    """

    def __init__(
        self,
        n_fourier: int = 128,
        hidden_dim: int = 256,
        n_layers: int = 6,
        lambda_pde: float = 1.0,
        lambda_bc: float = 0.5,
        lambda_ic: float = 1.0,
        device: str = "cpu",
    ):
        self.lambda_pde = lambda_pde
        self.lambda_bc = lambda_bc
        self.lambda_ic = lambda_ic
        self.device_str = device
        self._model: Any = None
        self._optimizer: Any = None
        self._trained = False
        self._n_fourier = n_fourier
        self._hidden_dim = hidden_dim
        self._n_layers = n_layers
        self._training_history: List[Dict[str, float]] = []

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        if not _HAS_TORCH:
            raise RuntimeError("PyTorch required for PINN")
        device = torch.device(self.device_str)
        self._model = PINNNetwork(
            n_fourier=self._n_fourier,
            hidden_dim=self._hidden_dim,
            n_layers=self._n_layers,
        ).to(device)
        self._optimizer = optim.Adam(self._model.parameters(), lr=1e-3)
        return self._model

    def train(
        self,
        observations: List[SpreadObservation],
        terrain: Optional[TerrainParams] = None,
        n_collocation: int = 5000,
        n_boundary: int = 500,
        n_initial: int = 500,
        epochs: int = 1000,
        lr: float = 1e-3,
    ) -> Dict[str, Any]:
        """Train the PINN on observed spread data.

        Args:
            observations: list of spread intensity observations
            terrain: terrain parameters (wind, diffusion)
            n_collocation: number of PDE collocation points
            n_boundary: number of boundary condition points
            n_initial: number of initial condition points
            epochs: training epochs
            lr: learning rate

        Returns:
            dict with training metrics
        """
        if not _HAS_TORCH:
            raise RuntimeError("PyTorch required")

        model = self._ensure_model()
        device = torch.device(self.device_str)
        self._optimizer = optim.Adam(model.parameters(), lr=lr)
        terrain = terrain or TerrainParams()

        # Initialise physics parameters from terrain
        with torch.no_grad():
            model.log_diffusion.fill_(math.log(max(terrain.diffusion_base, 1e-6)))
            model.vx.fill_(terrain.wind_speed_x * 0.001)  # scale to model units
            model.vy.fill_(terrain.wind_speed_y * 0.001)

        # Prepare observation data
        obs_data = np.array([[o.x, o.y, o.t] for o in observations], dtype=np.float32)
        obs_vals = np.array([[o.intensity] for o in observations], dtype=np.float32)

        # Normalise spatial-temporal domain to [0, 1]
        x_min, x_max = obs_data[:, 0].min(), obs_data[:, 0].max()
        y_min, y_max = obs_data[:, 1].min(), obs_data[:, 1].max()
        t_min, t_max = obs_data[:, 2].min(), obs_data[:, 2].max()

        x_range = max(x_max - x_min, 1e-6)
        y_range = max(y_max - y_min, 1e-6)
        t_range = max(t_max - t_min, 1e-6)

        obs_data[:, 0] = (obs_data[:, 0] - x_min) / x_range
        obs_data[:, 1] = (obs_data[:, 1] - y_min) / y_range
        obs_data[:, 2] = (obs_data[:, 2] - t_min) / t_range

        self._norm_params = {
            "x_min": float(x_min), "x_range": float(x_range),
            "y_min": float(y_min), "y_range": float(y_range),
            "t_min": float(t_min), "t_range": float(t_range),
        }

        obs_tensor = torch.tensor(obs_data, dtype=torch.float32, device=device)
        obs_vals_tensor = torch.tensor(obs_vals, dtype=torch.float32, device=device)

        # Generate collocation points (interior of the domain)
        colloc = torch.rand(n_collocation, 3, device=device)

        # Boundary points (edges of spatial domain)
        bc_points = self._generate_boundary_points(n_boundary, device)

        # Initial condition points (t = 0)
        ic_points = torch.rand(n_initial, 3, device=device)
        ic_points[:, 2] = 0.0  # t = 0

        self._training_history = []
        scheduler = optim.lr_scheduler.CosineAnnealingLR(self._optimizer, T_max=epochs)

        for epoch in range(1, epochs + 1):
            model.train()

            # 1. Data loss
            u_pred = model(obs_tensor)
            loss_data = torch.mean((u_pred - obs_vals_tensor) ** 2)

            # 2. PDE residual loss (physics constraint)
            residual = compute_pde_residual(model, colloc)
            loss_pde = torch.mean(residual ** 2)

            # 3. Boundary condition loss (u → 0 at boundaries)
            u_bc = model(bc_points)
            loss_bc = torch.mean(u_bc ** 2)

            # 4. Initial condition loss
            u_ic = model(ic_points)
            # At t=0, intensity should be concentrated at source(s)
            ic_target = torch.zeros_like(u_ic)
            loss_ic = torch.mean((u_ic - ic_target) ** 2)

            # Total loss
            total_loss = (
                loss_data
                + self.lambda_pde * loss_pde
                + self.lambda_bc * loss_bc
                + self.lambda_ic * loss_ic
            )

            self._optimizer.zero_grad()
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            self._optimizer.step()
            scheduler.step()

            if epoch % 100 == 0 or epoch == 1:
                metrics = {
                    "epoch": epoch,
                    "total_loss": total_loss.item(),
                    "data_loss": loss_data.item(),
                    "pde_loss": loss_pde.item(),
                    "bc_loss": loss_bc.item(),
                    "ic_loss": loss_ic.item(),
                    "diffusion": model.diffusion.item(),
                    "vx": model.vx.item(),
                    "vy": model.vy.item(),
                }
                self._training_history.append(metrics)
                logger.info(
                    "PINN epoch %d: total=%.4f data=%.4f pde=%.4f bc=%.4f ic=%.4f D=%.4f",
                    epoch, total_loss.item(), loss_data.item(), loss_pde.item(),
                    loss_bc.item(), loss_ic.item(), model.diffusion.item(),
                )

        self._trained = True
        return {
            "epochs": epochs,
            "final_loss": self._training_history[-1] if self._training_history else {},
            "learned_diffusion": model.diffusion.item(),
            "learned_velocity": (model.vx.item(), model.vy.item()),
        }

    def _generate_boundary_points(self, n: int, device: Any) -> Any:
        """Generate boundary condition points on the edges of the [0,1] domain."""
        if not _HAS_TORCH:
            return None
        points = []
        n_per_edge = n // 4
        # Left edge (x=0)
        p = torch.rand(n_per_edge, 3, device=device)
        p[:, 0] = 0.0
        points.append(p)
        # Right edge (x=1)
        p = torch.rand(n_per_edge, 3, device=device)
        p[:, 0] = 1.0
        points.append(p)
        # Bottom edge (y=0)
        p = torch.rand(n_per_edge, 3, device=device)
        p[:, 1] = 0.0
        points.append(p)
        # Top edge (y=1)
        p = torch.rand(n_per_edge, 3, device=device)
        p[:, 1] = 1.0
        points.append(p)
        return torch.cat(points, dim=0)

    def predict(
        self,
        points: List[Tuple[float, float, float]],
    ) -> List[Dict[str, Any]]:
        """Predict spread intensity at given (x, y, t) points.

        Args:
            points: list of (x, y, t) tuples

        Returns:
            list of dicts with x, y, t, intensity, confidence
        """
        if not _HAS_TORCH or self._model is None:
            raise RuntimeError("PINN model not trained or PyTorch unavailable")

        model = self._model
        model.eval()
        device = torch.device(self.device_str)
        norm = getattr(self, "_norm_params", None)

        pts = np.array(points, dtype=np.float32)
        if norm:
            pts[:, 0] = (pts[:, 0] - norm["x_min"]) / norm["x_range"]
            pts[:, 1] = (pts[:, 1] - norm["y_min"]) / norm["y_range"]
            pts[:, 2] = (pts[:, 2] - norm["t_min"]) / norm["t_range"]

        pts_tensor = torch.tensor(pts, dtype=torch.float32, device=device)

        with torch.no_grad():
            u = model(pts_tensor).cpu().numpy().flatten()

        results = []
        for i, (x, y, t) in enumerate(points):
            intensity = float(np.clip(u[i], 0, 1))
            results.append({
                "x": x,
                "y": y,
                "t": t,
                "intensity": round(intensity, 4),
                "confidence": round(1.0 - abs(intensity - 0.5) * 0.4, 2),  # heuristic confidence
            })
        return results

    def predict_grid(
        self,
        x_range: Tuple[float, float],
        y_range: Tuple[float, float],
        t: float,
        resolution: int = 50,
    ) -> Dict[str, Any]:
        """Predict intensity on a 2D grid at a given time.

        Returns a grid suitable for heatmap rendering.
        """
        xs = np.linspace(x_range[0], x_range[1], resolution)
        ys = np.linspace(y_range[0], y_range[1], resolution)
        points = [(float(x), float(y), t) for y in ys for x in xs]
        predictions = self.predict(points)

        grid = np.array([p["intensity"] for p in predictions]).reshape(resolution, resolution)

        return {
            "grid": grid.tolist(),
            "x_range": list(x_range),
            "y_range": list(y_range),
            "time": t,
            "resolution": resolution,
            "learned_physics": {
                "diffusion": self._model.diffusion.item() if self._model else 0,
                "velocity_x": self._model.vx.item() if self._model else 0,
                "velocity_y": self._model.vy.item() if self._model else 0,
            },
        }

    def save(self, path: Optional[Path] = None) -> Path:
        path = path or PINN_CHECKPOINT
        path.parent.mkdir(parents=True, exist_ok=True)
        if _HAS_TORCH and self._model is not None:
            torch.save({
                "model_state": self._model.state_dict(),
                "norm_params": getattr(self, "_norm_params", {}),
                "training_history": self._training_history,
            }, path)
        logger.info("PINN checkpoint saved to %s", path)
        return path

    def load(self, path: Optional[Path] = None) -> None:
        path = path or PINN_CHECKPOINT
        if not _HAS_TORCH or not path.exists():
            return
        model = self._ensure_model()
        checkpoint = torch.load(path, map_location=self.device_str, weights_only=False)
        model.load_state_dict(checkpoint["model_state"])
        self._norm_params = checkpoint.get("norm_params", {})
        self._training_history = checkpoint.get("training_history", [])
        self._trained = True
        logger.info("PINN checkpoint loaded from %s", path)

    @property
    def is_trained(self) -> bool:
        return self._trained


# ── Synthetic Data Generator (for testing) ────────────────────────────────────

def generate_synthetic_spread_data(
    n_observations: int = 500,
    diffusion: float = 0.02,
    wind_x: float = 0.5,
    wind_y: float = 0.2,
    source_x: float = 0.0,
    source_y: float = 0.0,
    t_max: float = 24.0,
    seed: int = 42,
) -> Tuple[List[SpreadObservation], TerrainParams]:
    """Generate synthetic disaster spread data from an analytical solution.

    Uses a Gaussian plume model as ground truth:
        u(x,y,t) = (1/(4πDt)) · exp(-(|r - r₀ - v·t|² / (4·D·t)))

    with added noise.
    """
    rng = np.random.RandomState(seed)
    terrain = TerrainParams(
        diffusion_base=diffusion,
        wind_speed_x=wind_x,
        wind_speed_y=wind_y,
    )

    observations = []
    for _ in range(n_observations):
        t = rng.uniform(0.1, t_max)
        x = rng.uniform(-5, 5)
        y = rng.uniform(-5, 5)

        # Gaussian plume solution
        dx = x - source_x - wind_x * t * 0.01
        dy = y - source_y - wind_y * t * 0.01
        r2 = dx ** 2 + dy ** 2
        intensity = (1.0 / (4 * math.pi * diffusion * max(t, 0.1))) * math.exp(-r2 / (4 * diffusion * max(t, 0.1)))
        intensity = min(intensity, 1.0)
        intensity += rng.normal(0, 0.02)  # noise
        intensity = max(0.0, min(1.0, intensity))

        observations.append(SpreadObservation(x=x, y=y, t=t, intensity=intensity))

    return observations, terrain


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    observations, terrain = generate_synthetic_spread_data(n_observations=500)
    print(f"Generated {len(observations)} observations")

    pinn = PINNSpreadModel(lambda_pde=1.0, lambda_bc=0.5, lambda_ic=1.0)
    result = pinn.train(observations, terrain, epochs=500)
    print(f"Training complete. Final loss: {result['final_loss']}")
    print(f"Learned diffusion: {result['learned_diffusion']:.4f} (true: {terrain.diffusion_base})")
    print(f"Learned velocity: {result['learned_velocity']}")

    pinn.save()
