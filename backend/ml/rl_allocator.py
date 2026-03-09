"""
Reinforcement Learning Resource Allocator — DQN / Double-DQN Agent.

Learns an allocation policy where:
  State  = (resource_availability, request_priority, distance_km,
            resource_type_encoded, urgency_level, time_pressure)
  Action = index of the resource to allocate to a given request
  Reward = +coverage_improvement − penalty_for_delay − distance_penalty

Components
──────────
- ``ReplayBuffer``       — experience-replay memory (uniform sampling)
- ``QNetwork``           — dueling architecture Q-network (PyTorch)
- ``DQNAgent``           — Double-DQN agent with ε-greedy exploration
- ``RLAllocationEnv``    — lightweight Gym-like environment for allocation
- ``RLAllocator``        — high-level API consumed by the FastAPI router
- ``train_rl``           — offline training entry-point

Usage from the API layer::

    allocator = RLAllocator()
    result = allocator.allocate(resources, requests, disaster_id)
"""

from __future__ import annotations

import copy
import logging
import math
import os
import random
from collections import deque, namedtuple
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torch.optim as optim
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False
    logger.warning("PyTorch not available — RL allocator will use heuristic fallback")

_MODEL_DIR = Path(__file__).resolve().parent / "models"
DEFAULT_RL_CHECKPOINT = _MODEL_DIR / "rl_allocator.pt"

# ── Transition tuple for replay buffer ────────────────────────────────────────

Transition = namedtuple("Transition", ["state", "action", "reward", "next_state", "done"])

# Resource type encoding (shared with GAT)
RESOURCE_TYPES = [
    "food", "water", "medical", "shelter", "clothing",
    "sanitation", "communication", "transport",
]
_TYPE_TO_IDX: Dict[str, int] = {t: i for i, t in enumerate(RESOURCE_TYPES)}

STATE_DIM = 10  # see _build_state
ACTION_DIM_DEFAULT = 64  # max resources we consider per step


# ── Replay Buffer ─────────────────────────────────────────────────────────────

class ReplayBuffer:
    """Fixed-size ring buffer for experience replay."""

    def __init__(self, capacity: int = 100_000):
        self.buffer: deque[Transition] = deque(maxlen=capacity)

    def push(self, *args: Any) -> None:
        self.buffer.append(Transition(*args))

    def sample(self, batch_size: int) -> List[Transition]:
        return random.sample(self.buffer, min(batch_size, len(self.buffer)))

    def __len__(self) -> int:
        return len(self.buffer)


# ── Dueling Q-Network ────────────────────────────────────────────────────────

if _HAS_TORCH:
    class QNetwork(nn.Module):
        """Dueling DQN architecture.

        Splits the final layers into a *value stream* and an *advantage stream*
        so that the network can learn the state value independently of the
        action advantages.

            Q(s, a) = V(s) + A(s, a) − mean(A(s, ·))
        """

        def __init__(self, state_dim: int = STATE_DIM, action_dim: int = ACTION_DIM_DEFAULT, hidden: int = 256):
            super().__init__()
            self.feature = nn.Sequential(
                nn.Linear(state_dim, hidden),
                nn.ReLU(),
                nn.Linear(hidden, hidden),
                nn.ReLU(),
            )
            self.value_stream = nn.Sequential(
                nn.Linear(hidden, hidden // 2),
                nn.ReLU(),
                nn.Linear(hidden // 2, 1),
            )
            self.advantage_stream = nn.Sequential(
                nn.Linear(hidden, hidden // 2),
                nn.ReLU(),
                nn.Linear(hidden // 2, action_dim),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            features = self.feature(x)
            value = self.value_stream(features)
            advantage = self.advantage_stream(features)
            # Combine via dueling formula
            q_values = value + advantage - advantage.mean(dim=-1, keepdim=True)
            return q_values
else:
    QNetwork = None  # type: ignore[assignment,misc]


# ── Reward Function ──────────────────────────────────────────────────────────

def compute_reward(
    coverage_before: float,
    coverage_after: float,
    distance_km: float,
    delay_hours: float = 0.0,
    type_match: bool = True,
) -> float:
    """Compute the scalar reward for a single allocation step.

    Reward = coverage_improvement − distance_penalty − delay_penalty + type_match_bonus

    Args:
        coverage_before: fraction of needs covered before this allocation (0-1)
        coverage_after: fraction of needs covered after this allocation (0-1)
        distance_km: distance between resource and disaster zone
        delay_hours: hours elapsed since request was made
        type_match: whether the allocated resource type matches the request
    """
    coverage_improvement = (coverage_after - coverage_before) * 10.0  # scale up
    distance_penalty = min(distance_km / 100.0, 2.0)  # cap at 2
    delay_penalty = min(delay_hours / 24.0, 1.5)  # cap at 1.5
    type_bonus = 1.0 if type_match else -0.5
    return coverage_improvement - distance_penalty - delay_penalty + type_bonus


# ── Gym-like Allocation Environment ──────────────────────────────────────────

@dataclass
class ResourceState:
    """Representation of a single resource for the RL environment."""
    id: str
    resource_type: str
    quantity: float
    lat: float
    lon: float
    priority: int = 5
    allocated: bool = False


@dataclass
class RequestState:
    """Representation of a single request/need."""
    id: str
    resource_type: str
    quantity_needed: float
    urgency: int = 5
    lat: float = 0.0
    lon: float = 0.0
    hours_waiting: float = 0.0
    fulfilled: bool = False


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Cheap haversine distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _build_state(
    resource: ResourceState,
    request: RequestState,
    n_available: int,
    n_pending: int,
) -> np.ndarray:
    """Build the state vector for a (resource, request) pair.

    Features (STATE_DIM = 10):
      0: resource quantity (normalised)
      1: resource priority (normalised 0-1)
      2: resource type one-hot index (normalised)
      3: request urgency (normalised 0-1)
      4: request quantity needed (normalised)
      5: distance_km (log-scaled)
      6: type_match (0 or 1)
      7: hours_waiting (log-scaled)
      8: available_ratio (n_available / max(n_available + n_pending, 1))
      9: request type index (normalised)
    """
    dist = _haversine(resource.lat, resource.lon, request.lat, request.lon)
    type_match = 1.0 if resource.resource_type.lower() == request.resource_type.lower() else 0.0
    res_type_idx = _TYPE_TO_IDX.get(resource.resource_type.lower(), len(RESOURCE_TYPES)) / max(len(RESOURCE_TYPES), 1)
    req_type_idx = _TYPE_TO_IDX.get(request.resource_type.lower(), len(RESOURCE_TYPES)) / max(len(RESOURCE_TYPES), 1)
    avail_ratio = n_available / max(n_available + n_pending, 1)

    return np.array([
        min(resource.quantity / 1000.0, 1.0),
        resource.priority / 10.0,
        res_type_idx,
        request.urgency / 10.0,
        min(request.quantity_needed / 1000.0, 1.0),
        math.log1p(dist) / 10.0,
        type_match,
        math.log1p(request.hours_waiting) / 5.0,
        avail_ratio,
        req_type_idx,
    ], dtype=np.float32)


class RLAllocationEnv:
    """Lightweight environment that presents (request, candidate_resources)
    pairs and expects an action = index of the chosen resource."""

    def __init__(
        self,
        resources: List[ResourceState],
        requests: List[RequestState],
        max_candidates: int = ACTION_DIM_DEFAULT,
    ):
        self.all_resources = resources
        self.all_requests = requests
        self.max_candidates = max_candidates
        self.reset()

    def reset(self) -> Tuple[np.ndarray, dict]:
        """Reset the environment to the initial state."""
        for r in self.all_resources:
            r.allocated = False
        for req in self.all_requests:
            req.fulfilled = False
        self._request_idx = 0
        self._total_reward = 0.0
        self._coverage_history: List[float] = [0.0]
        return self._get_obs(), {}

    @property
    def current_request(self) -> Optional[RequestState]:
        pending = [r for r in self.all_requests if not r.fulfilled]
        if not pending:
            return None
        return pending[0]

    def _available_resources(self) -> List[ResourceState]:
        return [r for r in self.all_resources if not r.allocated]

    def _get_candidates(self) -> List[ResourceState]:
        """Return up to max_candidates available resources, sorted by distance to current request."""
        req = self.current_request
        if req is None:
            return []
        avail = self._available_resources()
        avail.sort(key=lambda r: _haversine(r.lat, r.lon, req.lat, req.lon))
        return avail[:self.max_candidates]

    def _coverage(self) -> float:
        fulfilled = sum(1 for r in self.all_requests if r.fulfilled)
        return fulfilled / max(len(self.all_requests), 1)

    def _get_obs(self) -> np.ndarray:
        """Build observation for the current request + best candidate."""
        req = self.current_request
        candidates = self._get_candidates()
        n_avail = len(self._available_resources())
        n_pending = sum(1 for r in self.all_requests if not r.fulfilled)

        if req is None or not candidates:
            return np.zeros(STATE_DIM, dtype=np.float32)
        return _build_state(candidates[0], req, n_avail, n_pending)

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """Execute an allocation action.

        Args:
            action: index into the candidate list returned by _get_candidates()

        Returns:
            (obs, reward, terminated, truncated, info)
        """
        req = self.current_request
        candidates = self._get_candidates()

        if req is None or not candidates:
            return np.zeros(STATE_DIM, dtype=np.float32), 0.0, True, False, {}

        action = min(action, len(candidates) - 1)
        chosen = candidates[action]

        coverage_before = self._coverage()

        # Perform allocation
        chosen.allocated = True
        type_match = chosen.resource_type.lower() == req.resource_type.lower()
        if type_match and chosen.quantity >= req.quantity_needed:
            req.fulfilled = True

        coverage_after = self._coverage()
        dist = _haversine(chosen.lat, chosen.lon, req.lat, req.lon)

        reward = compute_reward(
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            distance_km=dist,
            delay_hours=req.hours_waiting,
            type_match=type_match,
        )

        self._total_reward += reward
        self._coverage_history.append(coverage_after)

        # Check termination
        done = self.current_request is None or not self._available_resources()

        obs = self._get_obs()
        info = {
            "resource_id": chosen.id,
            "request_id": req.id,
            "distance_km": dist,
            "type_match": type_match,
            "coverage": coverage_after,
        }
        return obs, reward, done, False, info

    @property
    def action_space_n(self) -> int:
        return self.max_candidates


# ── Double-DQN Agent ─────────────────────────────────────────────────────────

class DQNAgent:
    """Double-DQN agent with ε-greedy exploration and target network.

    Implements:
    - Experience replay (uniform sampling)
    - Double-DQN: action selection with online net, evaluation with target net
    - Dueling architecture (via QNetwork)
    - Soft target updates (Polyak averaging)
    """

    def __init__(
        self,
        state_dim: int = STATE_DIM,
        action_dim: int = ACTION_DIM_DEFAULT,
        lr: float = 1e-4,
        gamma: float = 0.99,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.05,
        epsilon_decay: int = 10_000,
        buffer_size: int = 100_000,
        batch_size: int = 64,
        tau: float = 0.005,
        device: str = "cpu",
    ):
        if not _HAS_TORCH:
            raise RuntimeError("PyTorch is required for DQNAgent")

        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.epsilon_start = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.batch_size = batch_size
        self.tau = tau
        self.device = torch.device(device)
        self.steps_done = 0

        # Networks
        self.policy_net = QNetwork(state_dim, action_dim).to(self.device)
        self.target_net = QNetwork(state_dim, action_dim).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=lr)
        self.replay_buffer = ReplayBuffer(buffer_size)

        # Training metrics
        self.training_losses: List[float] = []
        self.episode_rewards: List[float] = []

    @property
    def epsilon(self) -> float:
        """Current ε for ε-greedy exploration (exponential decay)."""
        return self.epsilon_end + (self.epsilon_start - self.epsilon_end) * \
            math.exp(-self.steps_done / self.epsilon_decay)

    def select_action(self, state: np.ndarray, n_valid_actions: int) -> int:
        """Select action using ε-greedy policy.

        Args:
            state: current state vector
            n_valid_actions: number of actually valid actions (may be < action_dim)
        """
        self.steps_done += 1
        if random.random() < self.epsilon:
            return random.randint(0, max(n_valid_actions - 1, 0))

        with torch.no_grad():
            state_t = torch.tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
            q_values = self.policy_net(state_t).squeeze(0)
            # Mask invalid actions
            if n_valid_actions < self.action_dim:
                q_values[n_valid_actions:] = -float("inf")
            return int(q_values.argmax().item())

    def store_transition(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> None:
        self.replay_buffer.push(state, action, reward, next_state, done)

    def train_step(self) -> Optional[float]:
        """Perform one gradient step on a batch from the replay buffer.

        Returns the loss value, or None if the buffer is too small.
        """
        if len(self.replay_buffer) < self.batch_size:
            return None

        batch = self.replay_buffer.sample(self.batch_size)
        states = torch.tensor(np.array([t.state for t in batch]), dtype=torch.float32, device=self.device)
        actions = torch.tensor([t.action for t in batch], dtype=torch.long, device=self.device).unsqueeze(1)
        rewards = torch.tensor([t.reward for t in batch], dtype=torch.float32, device=self.device)
        next_states = torch.tensor(np.array([t.next_state for t in batch]), dtype=torch.float32, device=self.device)
        dones = torch.tensor([t.done for t in batch], dtype=torch.float32, device=self.device)

        # Current Q values
        current_q = self.policy_net(states).gather(1, actions).squeeze(1)

        # Double-DQN: select best action with policy_net, evaluate with target_net
        with torch.no_grad():
            next_actions = self.policy_net(next_states).argmax(dim=1, keepdim=True)
            next_q = self.target_net(next_states).gather(1, next_actions).squeeze(1)
            target_q = rewards + self.gamma * next_q * (1.0 - dones)

        loss = F.smooth_l1_loss(current_q, target_q)

        self.optimizer.zero_grad()
        loss.backward()
        # Gradient clipping
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), max_norm=1.0)
        self.optimizer.step()

        # Soft update target network (Polyak averaging)
        with torch.no_grad():
            for p_target, p_policy in zip(self.target_net.parameters(), self.policy_net.parameters()):
                p_target.data.mul_(1.0 - self.tau).add_(p_policy.data * self.tau)

        loss_val = loss.item()
        self.training_losses.append(loss_val)
        return loss_val

    def save(self, path: Optional[Path] = None) -> Path:
        """Save model checkpoint."""
        path = path or DEFAULT_RL_CHECKPOINT
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "policy_net": self.policy_net.state_dict(),
            "target_net": self.target_net.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "steps_done": self.steps_done,
            "state_dim": self.state_dim,
            "action_dim": self.action_dim,
        }, path)
        logger.info("RL checkpoint saved to %s", path)
        return path

    def load(self, path: Optional[Path] = None) -> None:
        """Load model checkpoint."""
        path = path or DEFAULT_RL_CHECKPOINT
        if not path.exists():
            raise FileNotFoundError(f"No checkpoint at {path}")
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.policy_net.load_state_dict(checkpoint["policy_net"])
        self.target_net.load_state_dict(checkpoint["target_net"])
        self.optimizer.load_state_dict(checkpoint["optimizer"])
        self.steps_done = checkpoint.get("steps_done", 0)
        logger.info("RL checkpoint loaded from %s (steps=%d)", path, self.steps_done)


# ── High-Level Allocator ─────────────────────────────────────────────────────

class RLAllocator:
    """Production-ready RL-based resource allocator.

    Wraps the DQN agent and provides a simple ``allocate()`` method
    that accepts raw resource + request dicts from the database.
    """

    def __init__(self, checkpoint: Optional[Path] = None):
        self._agent: Optional[DQNAgent] = None
        self._checkpoint = checkpoint or DEFAULT_RL_CHECKPOINT
        self._loaded = False

    def _ensure_loaded(self) -> Optional[DQNAgent]:
        """Lazy-load the trained agent (returns None if no checkpoint)."""
        if self._loaded:
            return self._agent
        self._loaded = True
        if not _HAS_TORCH:
            logger.warning("PyTorch not available — RL allocator disabled")
            return None
        if not self._checkpoint.exists():
            logger.info("No RL checkpoint at %s — will use heuristic", self._checkpoint)
            return None
        try:
            agent = DQNAgent()
            agent.load(self._checkpoint)
            agent.policy_net.eval()
            self._agent = agent
            return agent
        except Exception as exc:
            logger.error("Failed to load RL checkpoint: %s", exc)
            return None

    def allocate(
        self,
        resources: List[Dict[str, Any]],
        requests: List[Dict[str, Any]],
        disaster_id: str,
        location_cache: Optional[Dict[str, Tuple[float, float]]] = None,
        zone_lat: float = 0.0,
        zone_lon: float = 0.0,
    ) -> Dict[str, Any]:
        """Run RL-based allocation.

        Args:
            resources: list of resource dicts from DB
            requests: list of request/need dicts (type, quantity, priority)
            disaster_id: target disaster ID
            location_cache: {location_id: (lat, lon)}
            zone_lat/zone_lon: disaster zone coordinates

        Returns:
            dict with keys: allocations, coverage_pct, total_reward, method
        """
        location_cache = location_cache or {}

        # Build environment state objects
        res_states = []
        for r in resources:
            lat, lon = location_cache.get(r.get("location_id", ""), (0.0, 0.0))
            res_states.append(ResourceState(
                id=r.get("id", ""),
                resource_type=r.get("type", "other"),
                quantity=float(r.get("quantity", 0)),
                lat=lat,
                lon=lon,
                priority=int(r.get("priority", 5)),
            ))

        req_states = []
        for i, req in enumerate(requests):
            req_states.append(RequestState(
                id=f"req_{i}",
                resource_type=req.get("type", "other"),
                quantity_needed=float(req.get("quantity", 1)),
                urgency=int(req.get("priority", 5)),
                lat=zone_lat,
                lon=zone_lon,
                hours_waiting=float(req.get("hours_waiting", 0)),
            ))

        agent = self._ensure_loaded()

        if agent is not None:
            return self._allocate_with_agent(agent, res_states, req_states, disaster_id)
        else:
            return self._allocate_heuristic(res_states, req_states, disaster_id)

    def _allocate_with_agent(
        self,
        agent: DQNAgent,
        resources: List[ResourceState],
        requests: List[RequestState],
        disaster_id: str,
    ) -> Dict[str, Any]:
        """Use the trained DQN agent to allocate resources."""
        env = RLAllocationEnv(resources, requests)
        obs, _ = env.reset()
        allocations = []
        total_reward = 0.0

        while True:
            candidates = env._get_candidates()
            if env.current_request is None or not candidates:
                break

            n_valid = len(candidates)
            action = agent.select_action(obs, n_valid)
            obs, reward, done, _, info = env.step(action)
            total_reward += reward

            allocations.append({
                "resource_id": info["resource_id"],
                "request_id": info["request_id"],
                "type": env.all_requests[0].resource_type if env.all_requests else "unknown",
                "distance_km": round(info["distance_km"], 2),
                "type_match": info["type_match"],
                "coverage": round(info["coverage"], 4),
            })

            if done:
                break

        coverage = env._coverage()
        return {
            "disaster_id": disaster_id,
            "allocations": allocations,
            "coverage_pct": round(coverage * 100, 2),
            "total_reward": round(total_reward, 4),
            "method": "double_dqn",
            "steps": len(allocations),
        }

    def _allocate_heuristic(
        self,
        resources: List[ResourceState],
        requests: List[RequestState],
        disaster_id: str,
    ) -> Dict[str, Any]:
        """Greedy heuristic fallback: match by type + closest distance."""
        allocations = []
        used = set()

        for req in sorted(requests, key=lambda r: -r.urgency):
            best_r = None
            best_dist = float("inf")
            for r in resources:
                if r.id in used:
                    continue
                if r.resource_type.lower() == req.resource_type.lower():
                    d = _haversine(r.lat, r.lon, req.lat, req.lon)
                    if d < best_dist:
                        best_dist = d
                        best_r = r
            # Fallback: any type if exact match unavailable
            if best_r is None:
                for r in resources:
                    if r.id in used:
                        continue
                    d = _haversine(r.lat, r.lon, req.lat, req.lon)
                    if d < best_dist:
                        best_dist = d
                        best_r = r

            if best_r is not None:
                used.add(best_r.id)
                req.fulfilled = True
                allocations.append({
                    "resource_id": best_r.id,
                    "request_id": req.id,
                    "type": req.resource_type,
                    "distance_km": round(best_dist, 2),
                    "type_match": best_r.resource_type.lower() == req.resource_type.lower(),
                })

        coverage = sum(1 for r in requests if r.fulfilled) / max(len(requests), 1)
        return {
            "disaster_id": disaster_id,
            "allocations": allocations,
            "coverage_pct": round(coverage * 100, 2),
            "total_reward": 0.0,
            "method": "greedy_heuristic",
            "steps": len(allocations),
        }

    @property
    def is_trained(self) -> bool:
        return self._ensure_loaded() is not None


# ── Training Script ──────────────────────────────────────────────────────────

def _generate_synthetic_episode(
    n_resources: int = 20,
    n_requests: int = 8,
) -> Tuple[List[ResourceState], List[RequestState]]:
    """Generate a synthetic allocation scenario for training."""
    resources = []
    for i in range(n_resources):
        rtype = random.choice(RESOURCE_TYPES)
        resources.append(ResourceState(
            id=f"res_{i}",
            resource_type=rtype,
            quantity=float(random.randint(10, 500)),
            lat=random.uniform(-10, 10),
            lon=random.uniform(-10, 10),
            priority=random.randint(1, 10),
        ))

    requests = []
    for i in range(n_requests):
        rtype = random.choice(RESOURCE_TYPES)
        requests.append(RequestState(
            id=f"req_{i}",
            resource_type=rtype,
            quantity_needed=float(random.randint(5, 200)),
            urgency=random.randint(1, 10),
            lat=random.uniform(-5, 5),
            lon=random.uniform(-5, 5),
            hours_waiting=random.uniform(0, 48),
        ))

    return resources, requests


def train_rl(
    n_episodes: int = 2000,
    max_steps_per_episode: int = 50,
    checkpoint_every: int = 200,
    save_path: Optional[Path] = None,
) -> DQNAgent:
    """Train the DQN agent on synthetic allocation episodes.

    Args:
        n_episodes: total training episodes
        max_steps_per_episode: max allocation steps per episode
        checkpoint_every: save checkpoint every N episodes
        save_path: where to save the final model

    Returns:
        Trained DQNAgent
    """
    if not _HAS_TORCH:
        raise RuntimeError("PyTorch is required for RL training")

    save_path = save_path or DEFAULT_RL_CHECKPOINT
    agent = DQNAgent(
        state_dim=STATE_DIM,
        action_dim=ACTION_DIM_DEFAULT,
        lr=3e-4,
        gamma=0.99,
        epsilon_start=1.0,
        epsilon_end=0.05,
        epsilon_decay=max(n_episodes * 3, 5000),
        buffer_size=100_000,
        batch_size=64,
        tau=0.005,
    )

    logger.info("Starting RL training for %d episodes", n_episodes)
    best_reward = -float("inf")

    for episode in range(1, n_episodes + 1):
        resources, requests = _generate_synthetic_episode(
            n_resources=random.randint(10, 40),
            n_requests=random.randint(3, 15),
        )
        env = RLAllocationEnv(resources, requests)
        obs, _ = env.reset()
        episode_reward = 0.0

        for step in range(max_steps_per_episode):
            candidates = env._get_candidates()
            if env.current_request is None or not candidates:
                break

            n_valid = len(candidates)
            action = agent.select_action(obs, n_valid)
            next_obs, reward, done, _, info = env.step(action)

            agent.store_transition(obs, action, reward, next_obs, done)
            loss = agent.train_step()

            obs = next_obs
            episode_reward += reward

            if done:
                break

        agent.episode_rewards.append(episode_reward)

        if episode_reward > best_reward:
            best_reward = episode_reward

        if episode % checkpoint_every == 0:
            agent.save(save_path)
            avg_reward = np.mean(agent.episode_rewards[-checkpoint_every:])
            logger.info(
                "Episode %d/%d | avg_reward=%.2f | best=%.2f | ε=%.3f | buffer=%d",
                episode, n_episodes, avg_reward, best_reward,
                agent.epsilon, len(agent.replay_buffer),
            )

    agent.save(save_path)
    logger.info("RL training complete. Final checkpoint: %s", save_path)
    return agent


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    train_rl(n_episodes=2000)
