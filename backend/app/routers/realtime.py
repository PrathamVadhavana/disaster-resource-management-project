"""
Server-Sent Events (SSE) endpoint for realtime notifications.

Polls the DB at short intervals and pushes new/changed rows
to connected clients via SSE.

**Performance note:** Each connected client creates a persistent HTTP
connection that queries the database every ``_POLL_INTERVAL`` seconds.
For 100 concurrent users this means ~2,000 database reads/minute.
At research/demo scale this is acceptable.  For production, consider
migrating to Supabase ``onSnapshot`` listeners on the frontend
(see ``frontend/src/lib/supabase/client.ts`` which now exports
Supabase realtime subscriptions).
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.database import db_admin
from app.dependencies import _verify_supabase_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/realtime", tags=["Realtime SSE"])

# Poll interval in seconds
_POLL_INTERVAL = 3


def _serialize(obj):
    """JSON-safe serialisation for datetime / UUID etc."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


async def _event_stream(
    user_id: str,
    tables: list[str],
) -> AsyncGenerator[str, None]:
    """Yield SSE events whenever new rows appear in the requested tables."""
    # Track the latest timestamp we've seen per table
    watermarks: dict[str, str] = {}
    now_iso = datetime.now(UTC).isoformat()
    for t in tables:
        watermarks[t] = now_iso

    yield f"event: connected\ndata: {json.dumps({'tables': tables})}\n\n"

    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            for table in tables:
                since = watermarks[table]
                query = db_admin.table(table).select("*").order("created_at", desc=False).limit(50)
                # For notifications, filter by user (avoid composite index
                # requirement by NOT combining .eq() + .gte() server-side;
                # instead we filter by created_at client-side)
                if table == "notifications":
                    query = db_admin.table(table).select("*").eq("user_id", user_id).limit(100)

                resp = await query.async_execute()
                rows = resp.data or []

                # Client-side date filtering (avoids composite index)
                if table == "notifications":
                    rows = [r for r in rows if (r.get("created_at") or "") >= since]
                    rows.sort(key=lambda r: r.get("created_at", ""))
                    rows = rows[:50]
                else:
                    rows = [r for r in rows if (r.get("created_at") or "") >= since]
                for row in rows:
                    row_ts = row.get("created_at") or row.get("updated_at")
                    if row_ts and row_ts > since:
                        watermarks[table] = row_ts
                    payload = json.dumps(
                        {"table": table, "type": "INSERT", "row": row},
                        default=_serialize,
                    )
                    yield f"event: db_change\ndata: {payload}\n\n"

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("SSE poll error: %s", e)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"


@router.get("/events")
async def realtime_events(
    request: Request,
    tables: str = Query(
        "notifications",
        description="Comma-separated table names to watch (e.g. notifications,resource_requests)",
    ),
    token: str | None = Query(None, description="Supabase auth token (alternative to Authorization header)"),
):
    """Stream database change events via SSE.

    The frontend connects with:
    ```js
    const es = new EventSource('/api/realtime/events?tables=notifications&token=<sb-token>')
    es.addEventListener('db_change', (e) => { ... })
    ```
    """
    # Authenticate via query param OR header
    user_id: str | None = None
    if token:
        decoded = _verify_supabase_token(token)
        user_id = decoded["uid"]
    else:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            decoded = _verify_supabase_token(auth_header[7:])
            user_id = decoded["uid"]

    if not user_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Authentication required")

    table_list = [t.strip() for t in tables.split(",") if t.strip()]
    allowed = {
        "notifications",
        "resource_requests",
        "available_resources",
        "ingested_events",
        "alert_notifications",
        "disaster_messages",
        "disasters",
    }
    table_list = [t for t in table_list if t in allowed]
    if not table_list:
        table_list = ["notifications"]

    return StreamingResponse(
        _event_stream(user_id, table_list),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
