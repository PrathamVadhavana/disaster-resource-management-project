"""
Multi-Agent System for Disaster Coordination.

Implements a multi-agent architecture where specialised agents
collaborate to analyse disasters, allocate resources, and generate
coordinated response plans.

Agent Roles
───────────
- **CoordinatorAgent**: orchestrates the other agents, dispatches tasks
- **PredictorAgent**: severity forecasting & risk assessment (TFT/ML)
- **AllocatorAgent**: resource allocation (GAT + RL allocator)
- **AnalystAgent**: causal analysis & NLP triage
- **ResponderAgent**: DisasterGPT RAG for knowledge queries

Communication
─────────────
Agents communicate via a shared **Blackboard** (shared state dict)
and an asynchronous **MessageBus** for inter-agent messages.

Usage::

    system = MultiAgentSystem()
    result = await system.process_query(
        "What resources should we deploy to the flood in Zone A?"
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Agent Roles ──────────────────────────────────────────────────────────────

class AgentRole(str, Enum):
    COORDINATOR = "coordinator"
    PREDICTOR = "predictor"
    ALLOCATOR = "allocator"
    ANALYST = "analyst"
    RESPONDER = "responder"


# ── Message Protocol ─────────────────────────────────────────────────────────

@dataclass
class AgentMessage:
    """Message passed between agents via the message bus."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: AgentRole = AgentRole.COORDINATOR
    recipient: AgentRole = AgentRole.COORDINATOR
    msg_type: str = "request"  # request | response | broadcast
    content: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: Optional[str] = None  # links request → response


# ── Shared Blackboard ────────────────────────────────────────────────────────

class Blackboard:
    """Shared state accessible by all agents.

    The blackboard holds:
    - Current disaster context
    - Agent outputs (predictions, allocations, analyses)
    - Conversation history
    - Task status tracking
    """

    def __init__(self):
        self._state: Dict[str, Any] = {
            "disaster_context": {},
            "predictions": {},
            "allocations": {},
            "analyses": {},
            "conversation": [],
            "tasks": [],
        }
        self._lock = asyncio.Lock()

    async def read(self, key: str) -> Any:
        async with self._lock:
            return self._state.get(key)

    async def write(self, key: str, value: Any) -> None:
        async with self._lock:
            self._state[key] = value

    async def append(self, key: str, value: Any) -> None:
        async with self._lock:
            if key not in self._state:
                self._state[key] = []
            self._state[key].append(value)

    async def get_snapshot(self) -> Dict[str, Any]:
        async with self._lock:
            return dict(self._state)


# ── Message Bus ──────────────────────────────────────────────────────────────

class MessageBus:
    """Asynchronous message bus for inter-agent communication."""

    def __init__(self):
        self._queues: Dict[AgentRole, asyncio.Queue] = {}
        self._history: List[AgentMessage] = []

    def register(self, role: AgentRole) -> None:
        if role not in self._queues:
            self._queues[role] = asyncio.Queue()

    async def send(self, message: AgentMessage) -> None:
        self._history.append(message)
        if message.recipient in self._queues:
            await self._queues[message.recipient].put(message)
        elif message.msg_type == "broadcast":
            for role, q in self._queues.items():
                if role != message.sender:
                    await q.put(message)

    async def receive(self, role: AgentRole, timeout: float = 30.0) -> Optional[AgentMessage]:
        if role not in self._queues:
            return None
        try:
            return await asyncio.wait_for(self._queues[role].get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def get_history(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": m.id,
                "sender": m.sender.value,
                "recipient": m.recipient.value,
                "type": m.msg_type,
                "content_preview": str(m.content)[:200],
                "timestamp": m.timestamp,
            }
            for m in self._history
        ]


# ── Base Agent ───────────────────────────────────────────────────────────────

class BaseAgent:
    """Base class for all agents."""

    def __init__(self, role: AgentRole, blackboard: Blackboard, bus: MessageBus):
        self.role = role
        self.blackboard = blackboard
        self.bus = bus
        self.bus.register(role)

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process a task and return results. Override in subclasses."""
        raise NotImplementedError

    async def send_to(self, recipient: AgentRole, content: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        msg = AgentMessage(
            sender=self.role,
            recipient=recipient,
            msg_type="request",
            content=content,
            correlation_id=correlation_id,
        )
        await self.bus.send(msg)

    async def respond_to(self, original: AgentMessage, content: Dict[str, Any]) -> None:
        msg = AgentMessage(
            sender=self.role,
            recipient=original.sender,
            msg_type="response",
            content=content,
            correlation_id=original.id,
        )
        await self.bus.send(msg)


# ── Predictor Agent ──────────────────────────────────────────────────────────

class PredictorAgent(BaseAgent):
    """Agent for severity prediction and risk assessment.

    Uses TFT model (if available) or heuristic fallback for
    disaster severity and timeline forecasting.
    """

    def __init__(self, blackboard: Blackboard, bus: MessageBus):
        super().__init__(AgentRole.PREDICTOR, blackboard, bus)

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        disaster_type = task.get("disaster_type", "unknown")
        severity = task.get("severity", "medium")
        location = task.get("location", {})

        # Try ML model prediction
        try:
            from app.dependencies import get_ml_service
            ml_svc = get_ml_service()
            if ml_svc and hasattr(ml_svc, 'predict_severity'):
                prediction = await ml_svc.predict_severity(task)
                pred_sev = prediction.get("severity", severity)
                pred_conf = prediction.get("confidence", 0.7)
                pred_timeline = prediction.get("timeline_hours", 72)
                pred_factors = prediction.get("risk_factors", [])
                result = {
                    "agent": self.role.value,
                    "predicted_severity": pred_sev,
                    "confidence": pred_conf,
                    "risk_factors": pred_factors,
                    "timeline_hours": pred_timeline,
                    "method": "tft_model",
                    "summary": (
                        f"Severity predicted as **{pred_sev}** "
                        f"(confidence: {pred_conf:.0%}). "
                        f"Estimated timeline: {pred_timeline}h. "
                        + (f"Risk factors: {', '.join(pred_factors[:3])}." if pred_factors else "")
                    ),
                }
                await self.blackboard.write("predictions", result)
                return result
        except Exception as exc:
            logger.debug("ML prediction fallback: %s", exc)

        # Heuristic fallback
        severity_scores = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
        risk_score = severity_scores.get(severity, 0.5)

        type_risk = {
            "earthquake": 0.9, "flood": 0.7, "hurricane": 0.85,
            "wildfire": 0.75, "tsunami": 0.95, "tornado": 0.8,
        }
        risk_score = max(risk_score, type_risk.get(disaster_type.lower(), 0.5))

        timeline = 72 if risk_score > 0.7 else 48
        est_affected = int(risk_score * 10000)
        result = {
            "agent": self.role.value,
            "predicted_severity": severity,
            "confidence": round(risk_score, 2),
            "risk_factors": [
                f"Disaster type: {disaster_type}",
                f"Initial severity: {severity}",
            ],
            "timeline_hours": timeline,
            "estimated_affected": est_affected,
            "method": "heuristic",
            "summary": (
                f"Severity assessed as **{severity}** "
                f"(confidence: {risk_score:.0%}). "
                f"Estimated {est_affected:,} people affected over {timeline}h. "
                f"Disaster type: {disaster_type}."
            ),
        }
        await self.blackboard.write("predictions", result)
        return result


# ── Allocator Agent ──────────────────────────────────────────────────────────

class AllocatorAgent(BaseAgent):
    """Agent for resource allocation decisions.

    Uses GAT model, RL allocator, or LP solver to determine
    optimal resource distribution.
    """

    def __init__(self, blackboard: Blackboard, bus: MessageBus):
        super().__init__(AgentRole.ALLOCATOR, blackboard, bus)

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        disaster_id = task.get("disaster_id", "")
        required_resources = task.get("required_resources", [])
        predictions = await self.blackboard.read("predictions") or {}

        # Try RL allocator
        try:
            from ml.rl_allocator import RLAllocator
            rl = RLAllocator()
            if rl.is_trained:
                from app.database import db
                resp = db.table("resources").select("*").eq("status", "available").execute()
                resources = resp.data or []

                rl_result = rl.allocate(
                    resources=resources,
                    requests=required_resources,
                    disaster_id=disaster_id,
                )
                allocs = rl_result.get("allocations", [])
                coverage = rl_result.get("coverage_pct", 0)
                result = {
                    "agent": self.role.value,
                    "allocations": allocs,
                    "coverage_pct": coverage,
                    "method": rl_result.get("method", "rl"),
                    "informed_by_prediction": bool(predictions),
                    "summary": (
                        f"Allocated **{len(allocs)} resources** "
                        f"with **{coverage}%** coverage using RL optimisation."
                    ),
                }
                await self.blackboard.write("allocations", result)
                return result
        except Exception as exc:
            logger.debug("RL allocator fallback: %s", exc)

        # Heuristic based on predictions
        predicted_severity = predictions.get("predicted_severity", "medium")
        urgency_map = {"low": 3, "medium": 5, "high": 8, "critical": 10}
        urgency = urgency_map.get(predicted_severity, 5)

        recs = [
            {"type": "medical", "priority": urgency, "reason": "Based on severity prediction"},
            {"type": "food", "priority": max(urgency - 2, 1), "reason": "Essential supplies"},
            {"type": "shelter", "priority": max(urgency - 1, 1), "reason": "Displaced population"},
            {"type": "water", "priority": urgency, "reason": "Critical need"},
        ]
        rec_str = ", ".join(f"{r['type']} (priority {r['priority']})" for r in recs)
        result = {
            "agent": self.role.value,
            "recommended_urgency": urgency,
            "recommended_resources": recs,
            "method": "heuristic",
            "informed_by_prediction": bool(predictions),
            "summary": (
                f"Urgency level: **{urgency}/10**. "
                f"Recommended resources: {rec_str}."
            ),
        }
        await self.blackboard.write("allocations", result)
        return result


# ── Analyst Agent ────────────────────────────────────────────────────────────

class AnalystAgent(BaseAgent):
    """Agent for causal analysis and NLP assessment.

    Uses the DoWhy causal model for counterfactual analysis
    and NLP service for text triage.
    """

    def __init__(self, blackboard: Blackboard, bus: MessageBus):
        super().__init__(AgentRole.ANALYST, blackboard, bus)

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        disaster_id = task.get("disaster_id", "")
        query_text = task.get("query", "")

        analyses = {}

        # Try causal analysis
        try:
            from ml.causal_model import DisasterCausalModel
            cm = DisasterCausalModel()
            if disaster_id:
                from app.database import db
                resp = db.table("disasters").select("*").eq("id", disaster_id).maybe_single().execute()
                if resp.data:
                    disaster_data = resp.data
                    # Run counterfactual: what if response time was halved?
                    counterfactual = cm.counterfactual_query(
                        disaster_data=disaster_data,
                        intervention_var="response_time_hours",
                        intervention_val=max(float(disaster_data.get("response_time_hours", 12)) / 2, 1),
                        outcome_var="casualties",
                    )
                    analyses["causal"] = {
                        "counterfactual": counterfactual,
                        "insight": "Faster response could reduce casualties",
                    }
        except Exception as exc:
            logger.debug("Causal analysis skipped: %s", exc)
            analyses["causal"] = {"status": "unavailable", "reason": str(exc)}

        # NLP analysis of query
        if query_text:
            analyses["nlp"] = {
                "query_intent": self._classify_intent(query_text),
                "key_entities": self._extract_entities(query_text),
                "urgency_signals": self._detect_urgency(query_text),
            }

        # Build human-readable summary
        summary_parts: List[str] = []
        if "nlp" in analyses:
            nlp = analyses["nlp"]
            summary_parts.append(f"Query intent: **{nlp.get('query_intent', 'unknown')}**.")
            if nlp.get("key_entities"):
                summary_parts.append(f"Entities: {', '.join(nlp['key_entities'])}.")
            urg = nlp.get("urgency_signals", {})
            if urg.get("is_urgent"):
                summary_parts.append(f"⚠️ Urgency detected: {', '.join(urg['signals'])}.")
            else:
                summary_parts.append("No immediate urgency signals.")
        if "causal" in analyses:
            c = analyses["causal"]
            if c.get("status") == "unavailable":
                summary_parts.append("Causal analysis: data unavailable.")
            elif c.get("insight"):
                summary_parts.append(f"Causal insight: {c['insight']}.")

        result = {
            "agent": self.role.value,
            "analyses": analyses,
            "disaster_id": disaster_id,
            "summary": " ".join(summary_parts) if summary_parts else "Analysis completed.",
        }
        await self.blackboard.write("analyses", result)
        return result

    @staticmethod
    def _classify_intent(text: str) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in ["allocate", "deploy", "send", "resource"]):
            return "resource_allocation"
        if any(w in text_lower for w in ["predict", "forecast", "expect", "severity"]):
            return "prediction"
        if any(w in text_lower for w in ["cause", "why", "reason", "factor"]):
            return "causal_analysis"
        if any(w in text_lower for w in ["status", "update", "current"]):
            return "status_inquiry"
        return "general_inquiry"

    @staticmethod
    def _extract_entities(text: str) -> List[str]:
        entities = []
        disaster_types = ["earthquake", "flood", "hurricane", "wildfire", "tornado", "tsunami"]
        resource_types = ["food", "water", "medical", "shelter", "clothing"]
        for word in text.lower().split():
            if word in disaster_types:
                entities.append(f"disaster:{word}")
            if word in resource_types:
                entities.append(f"resource:{word}")
        return entities

    @staticmethod
    def _detect_urgency(text: str) -> Dict[str, Any]:
        urgent_words = ["urgent", "emergency", "critical", "immediately", "asap", "dying", "trapped"]
        text_lower = text.lower()
        signals = [w for w in urgent_words if w in text_lower]
        return {
            "is_urgent": len(signals) > 0,
            "signals": signals,
            "urgency_score": min(len(signals) / 3.0, 1.0),
        }


# ── Responder Agent ──────────────────────────────────────────────────────────

class ResponderAgent(BaseAgent):
    """Agent for knowledge-based response generation using DisasterGPT RAG.

    Synthesises outputs from all other agents into a coherent response.
    """

    def __init__(self, blackboard: Blackboard, bus: MessageBus):
        super().__init__(AgentRole.RESPONDER, blackboard, bus)

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        query = task.get("query", "")
        disaster_id = task.get("disaster_id")

        # Gather context from the blackboard
        snapshot = await self.blackboard.get_snapshot()
        predictions = snapshot.get("predictions", {})
        allocations = snapshot.get("allocations", {})
        analyses = snapshot.get("analyses", {})

        # Try RAG-based response
        rag_response = None
        try:
            from ml.disaster_rag import DisasterRAG
            rag = DisasterRAG()
            result = await rag.query(
                question=query,
                disaster_id=disaster_id,
                top_k=3,
                max_tokens=512,
            )
            rag_response = result.get("response", "")
        except Exception as exc:
            logger.debug("RAG query skipped: %s", exc)

        # Synthesise final response that integrates all agent outputs
        synthesis = self._synthesise(
            query=query,
            predictions=predictions,
            allocations=allocations,
            analyses=analyses,
            rag_response=rag_response,
        )

        result = {
            "agent": self.role.value,
            "response": synthesis["response"],
            "confidence": synthesis["confidence"],
            "sources": synthesis["sources"],
            "agent_contributions": synthesis["contributions"],
        }
        return result

    def _synthesise(
        self,
        query: str,
        predictions: Dict,
        allocations: Dict,
        analyses: Dict,
        rag_response: Optional[str],
    ) -> Dict[str, Any]:
        """Combine outputs from all agents into a unified response."""
        parts = []
        sources = []
        contributions = {}

        # Include predictions
        if predictions and predictions.get("predicted_severity"):
            severity = predictions["predicted_severity"]
            confidence = predictions.get("confidence", 0)
            parts.append(
                f"**Risk Assessment**: The disaster is assessed at {severity} severity "
                f"(confidence: {confidence:.0%}). "
                f"Estimated timeline: {predictions.get('timeline_hours', 'N/A')} hours."
            )
            sources.append("PredictorAgent")
            contributions["predictor"] = predictions

        # Include allocation recommendations
        if allocations:
            if allocations.get("allocations"):
                n_alloc = len(allocations["allocations"])
                coverage = allocations.get("coverage_pct", 0)
                parts.append(
                    f"**Resource Allocation**: {n_alloc} resources allocated "
                    f"with {coverage}% coverage (method: {allocations.get('method', 'N/A')})."
                )
            elif allocations.get("recommended_resources"):
                recs = allocations["recommended_resources"]
                rec_str = ", ".join(f"{r['type']} (priority {r['priority']})" for r in recs[:4])
                parts.append(f"**Recommended Resources**: {rec_str}.")
            sources.append("AllocatorAgent")
            contributions["allocator"] = allocations

        # Include analyses
        if analyses and analyses.get("analyses"):
            a = analyses["analyses"]
            if "nlp" in a:
                intent = a["nlp"].get("query_intent", "unknown")
                parts.append(f"**Analysis**: Query classified as '{intent}'.")
                urgency = a["nlp"].get("urgency_signals", {})
                if urgency.get("is_urgent"):
                    parts.append(f"⚠️ Urgency detected: {', '.join(urgency['signals'])}")
            if "causal" in a and "counterfactual" in a["causal"]:
                parts.append("**Causal Insight**: Counterfactual analysis available.")
            sources.append("AnalystAgent")
            contributions["analyst"] = analyses

        # Include RAG response
        if rag_response:
            parts.append(f"**Knowledge Base**: {rag_response[:500]}")
            sources.append("ResponderAgent/RAG")

        if not parts:
            response = f"I've analysed your query: \"{query}\". Based on available data, please provide a disaster ID or more context for a detailed multi-agent analysis."
        else:
            response = "\n\n".join(parts)

        # Overall confidence (average of available)
        conf_values = [
            predictions.get("confidence", 0.5) if predictions else 0.5,
        ]
        overall_conf = sum(conf_values) / len(conf_values)

        return {
            "response": response,
            "confidence": round(overall_conf, 2),
            "sources": sources,
            "contributions": contributions,
        }


# ── Coordinator Agent ────────────────────────────────────────────────────────

class CoordinatorAgent(BaseAgent):
    """Orchestrator agent that dispatches tasks to specialist agents.

    The coordinator:
    1. Analyses the incoming query/task
    2. Determines which agents to invoke
    3. Dispatches tasks in the right order
    4. Collects and synthesises results
    """

    def __init__(
        self,
        blackboard: Blackboard,
        bus: MessageBus,
        agents: Dict[AgentRole, BaseAgent],
    ):
        super().__init__(AgentRole.COORDINATOR, blackboard, bus)
        self.agents = agents

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Orchestrate the multi-agent pipeline for a given task."""
        query = task.get("query", "")
        disaster_id = task.get("disaster_id")

        await self.blackboard.write("disaster_context", {
            "query": query,
            "disaster_id": disaster_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        results = {}
        agent_sequence = self._plan_execution(task)

        for role in agent_sequence:
            agent = self.agents.get(role)
            if agent is None:
                continue
            try:
                agent_task = {**task}
                result = await agent.process(agent_task)
                results[role.value] = result
            except Exception as exc:
                logger.error("Agent %s failed: %s", role.value, exc)
                results[role.value] = {"error": str(exc)}

        return {
            "coordinator": self.role.value,
            "query": query,
            "disaster_id": disaster_id,
            "agent_results": results,
            "execution_order": [r.value for r in agent_sequence],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _plan_execution(self, task: Dict[str, Any]) -> List[AgentRole]:
        """Determine the agent execution order based on the task."""
        query = task.get("query", "").lower()

        # Default: run all agents in order
        plan = [AgentRole.ANALYST, AgentRole.PREDICTOR, AgentRole.ALLOCATOR, AgentRole.RESPONDER]

        # Optimise: skip unnecessary agents
        if "predict" in query or "forecast" in query or "severity" in query:
            plan = [AgentRole.PREDICTOR, AgentRole.RESPONDER]
        elif "allocat" in query or "resource" in query or "deploy" in query:
            plan = [AgentRole.PREDICTOR, AgentRole.ALLOCATOR, AgentRole.RESPONDER]
        elif "cause" in query or "why" in query or "factor" in query:
            plan = [AgentRole.ANALYST, AgentRole.RESPONDER]

        return plan


# ── Multi-Agent System (Top-Level) ───────────────────────────────────────────

class MultiAgentSystem:
    """Top-level multi-agent system for disaster coordination.

    Usage::

        system = MultiAgentSystem()
        result = await system.process_query("Deploy resources to flood zone A")
    """

    def __init__(self):
        self.blackboard = Blackboard()
        self.bus = MessageBus()

        # Create specialist agents
        self.predictor = PredictorAgent(self.blackboard, self.bus)
        self.allocator = AllocatorAgent(self.blackboard, self.bus)
        self.analyst = AnalystAgent(self.blackboard, self.bus)
        self.responder = ResponderAgent(self.blackboard, self.bus)

        # Create coordinator with access to all agents
        agents = {
            AgentRole.PREDICTOR: self.predictor,
            AgentRole.ALLOCATOR: self.allocator,
            AgentRole.ANALYST: self.analyst,
            AgentRole.RESPONDER: self.responder,
        }
        self.coordinator = CoordinatorAgent(self.blackboard, self.bus, agents)

    async def process_query(
        self,
        query: str,
        disaster_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Process a natural-language query through the multi-agent pipeline.

        Args:
            query: user's natural-language query
            disaster_id: optional disaster context
            **kwargs: additional task parameters

        Returns:
            dict with coordinated response from all agents
        """
        task = {
            "query": query,
            "disaster_id": disaster_id,
            **kwargs,
        }
        return await self.coordinator.process(task)

    async def process_query_stream(
        self,
        query: str,
        disaster_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Streaming version — yields SSE events as agents complete work.

        Each event is a JSON string with:
          {"type": "agent_start|agent_result|final", "agent": "...", "data": {...}}
        """
        task = {
            "query": query,
            "disaster_id": disaster_id,
            **kwargs,
        }

        agent_sequence = self.coordinator._plan_execution(task)

        for role in agent_sequence:
            agent = self.coordinator.agents.get(role)
            if agent is None:
                continue

            yield json.dumps({
                "type": "agent_start",
                "agent": role.value,
                "message": f"Agent '{role.value}' is processing...",
            })

            try:
                result = await agent.process(task)
                yield json.dumps({
                    "type": "agent_result",
                    "agent": role.value,
                    "data": result,
                })
            except Exception as exc:
                yield json.dumps({
                    "type": "agent_error",
                    "agent": role.value,
                    "error": str(exc),
                })

        # Final synthesis
        snapshot = await self.blackboard.get_snapshot()
        yield json.dumps({
            "type": "final",
            "data": {
                "query": query,
                "disaster_id": disaster_id,
                "execution_order": [r.value for r in agent_sequence],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })

    async def get_status(self) -> Dict[str, Any]:
        """Return the status of all agents."""
        return {
            "agents": [
                {"role": role.value, "status": "active"}
                for role in AgentRole
                if role != AgentRole.COORDINATOR
            ],
            "coordinator": "active",
            "message_history_size": len(self.bus.get_history()),
        }


# ── Singleton accessor ──────────────────────────────────────────────────────

_system_instance: Optional[MultiAgentSystem] = None


def get_multi_agent_system() -> MultiAgentSystem:
    """Return a lazily-initialised singleton MultiAgentSystem."""
    global _system_instance
    if _system_instance is None:
        _system_instance = MultiAgentSystem()
    return _system_instance
