"""
Event Sourcing for Audit Trail.

Every state change on a request emits an immutable event. This replaces ad-hoc
operational_pulse logging with proper event sourcing for:
- Complete audit trail
- Replay for debugging
- Richer data feed for anomaly detection

Events are buffered in-memory and flushed in batches to reduce database writes.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.database import db_admin

logger = logging.getLogger("event_sourcing")

# ── Event buffer for batch writes ─────────────────────────────────────────────

_event_buffer: list[dict[str, Any]] = []
_buffer_lock = asyncio.Lock() if hasattr(asyncio, "Lock") else None
_BUFFER_MAX_SIZE = 20  # Flush after this many events
_BUFFER_FLUSH_INTERVAL = 30  # Flush every 30 seconds regardless


async def _flush_event_buffer() -> int:
    """Write all buffered events to the database in a single batch insert."""
    global _event_buffer
    if not _event_buffer:
        return 0

    events_to_write = _event_buffer[:]
    _event_buffer = []

    try:
        await db_admin.table("event_store").insert(events_to_write).async_execute()
        logger.debug("Flushed %d events to event_store", len(events_to_write))
        return len(events_to_write)
    except Exception as e:
        logger.debug("Event store batch write failed (non-blocking): %s", e)
        return 0


async def _maybe_flush():
    """Flush if buffer is full."""
    if len(_event_buffer) >= _BUFFER_MAX_SIZE:
        await _flush_event_buffer()


async def start_event_flush_loop():
    """Background loop that periodically flushes the event buffer."""
    while True:
        await asyncio.sleep(_BUFFER_FLUSH_INTERVAL)
        try:
            await _flush_event_buffer()
        except Exception as e:
            logger.debug("Event flush loop error: %s", e)


async def emit_event(
    entity_type: str,
    entity_id: str,
    event_type: str,
    actor_id: str | None = None,
    actor_role: str = "system",
    data: dict[str, Any] | None = None,
    old_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
) -> dict | None:
    """Emit an immutable event to the event store.

    Parameters
    ----------
    entity_type : str
        'request', 'disaster', 'resource', 'user'
    entity_id : str
        ID of the entity
    event_type : str
        e.g., 'request.created', 'request.status_changed', 'request.priority_escalated'
    actor_id : str, optional
        Who triggered the event
    actor_role : str
        'admin', 'victim', 'ngo', 'donor', 'volunteer', 'system'
    data : dict, optional
        Event-specific payload
    old_state : dict, optional
        Snapshot of relevant fields before the change
    new_state : dict, optional
        Snapshot of relevant fields after the change
    """
    try:
        event = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_type": event_type,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "data": data or {},
            "old_state": old_state or {},
            "new_state": new_state or {},
            "timestamp": datetime.now(UTC).isoformat(),
            "version": 1,
        }
        # Buffer the event instead of writing immediately
        _event_buffer.append(event)
        await _maybe_flush()
        return event
    except Exception as e:
        # Event store table may not exist yet — graceful degradation
        logger.debug("Event store write failed (non-blocking): %s", e)
        return None


async def get_entity_events(
    entity_type: str,
    entity_id: str,
    event_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Retrieve events for an entity."""
    try:
        query = (
            db_admin.table("event_store")
            .select("*")
            .eq("entity_type", entity_type)
            .eq("entity_id", entity_id)
            .order("timestamp", desc=False)
            .limit(limit)
        )
        if event_type:
            query = query.eq("event_type", event_type)
        resp = await query.async_execute()
        return resp.data or []
    except Exception:
        return []


async def get_events_since(
    since: str,
    entity_type: str | None = None,
    event_type: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Retrieve events since a timestamp (for replay/anomaly detection)."""
    try:
        query = (
            db_admin.table("event_store")
            .select("*")
            .gte("timestamp", since)
            .order("timestamp", desc=False)
            .limit(limit)
        )
        if entity_type:
            query = query.eq("entity_type", entity_type)
        if event_type:
            query = query.eq("event_type", event_type)
        resp = await query.async_execute()
        return resp.data or []
    except Exception:
        return []


# ── Convenience emitters for common events ────────────────────────────────


async def emit_request_created(request_id: str, actor_id: str, data: dict):
    return await emit_event(
        entity_type="request",
        entity_id=request_id,
        event_type="request.created",
        actor_id=actor_id,
        actor_role="victim",
        data=data,
    )


async def emit_request_status_changed(
    request_id: str,
    actor_id: str | None,
    actor_role: str,
    old_status: str,
    new_status: str,
    details: dict | None = None,
):
    return await emit_event(
        entity_type="request",
        entity_id=request_id,
        event_type="request.status_changed",
        actor_id=actor_id,
        actor_role=actor_role,
        data=details or {},
        old_state={"status": old_status},
        new_state={"status": new_status},
    )


async def emit_request_priority_escalated(
    request_id: str,
    old_priority: str,
    new_priority: str,
    reason: str,
):
    return await emit_event(
        entity_type="request",
        entity_id=request_id,
        event_type="request.priority_escalated",
        actor_role="system",
        data={"reason": reason},
        old_state={"priority": old_priority},
        new_state={"priority": new_priority},
    )


async def emit_fulfillment_contributed(
    request_id: str,
    provider_id: str,
    provider_role: str,
    contribution: dict,
):
    return await emit_event(
        entity_type="request",
        entity_id=request_id,
        event_type="request.fulfillment_contributed",
        actor_id=provider_id,
        actor_role=provider_role,
        data=contribution,
    )


async def emit_delivery_confirmed(
    request_id: str,
    victim_id: str,
    confirmation_data: dict,
):
    return await emit_event(
        entity_type="request",
        entity_id=request_id,
        event_type="request.delivery_confirmed",
        actor_id=victim_id,
        actor_role="victim",
        data=confirmation_data,
    )


async def emit_request_assigned(
    request_id: str,
    assigned_to: str,
    assigned_by: str,
    assigned_role: str = "ngo",
):
    return await emit_event(
        entity_type="request",
        entity_id=request_id,
        event_type="request.assigned",
        actor_id=assigned_by,
        actor_role="admin",
        data={"assigned_to": assigned_to, "assigned_role": assigned_role},
    )
