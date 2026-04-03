"""
Supabase database client with chainable query builder API.

Provides the same chainable query builder API as the previous
implementation:
    db.table("x").select("*").eq("col", val).order("col", desc=True).limit(10).execute()

All heavy lifting is delegated to the Supabase Python client which talks
directly to the PostgREST layer — no client-side sorting or filtering needed.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from supabase import Client, create_client

logger = logging.getLogger(__name__)


@dataclass
class APIResponse:
    """API response object returned by query execution."""

    data: Any = None
    count: int | None = None


# ── Supabase client (lazy singleton) ──────────────────────────────────────────
# The Supabase Python client is thread-safe — each query builds its own HTTP
# request via httpx, so no coarse-grained lock is needed.  The old _db_lock
# serialised every query and was the #1 latency bottleneck.

_supabase_client: Client | None = None
_init_lock_flag = False  # lightweight guard only during first-time init


def _get_sb() -> Client:
    """Return the Supabase client, creating it on first call (thread-safe init)."""
    global _supabase_client, _init_lock_flag
    if _supabase_client is not None:
        return _supabase_client
    # Only the very first creation needs a guard — use a simple flag.
    # Worst case two threads both create a client; that's harmless.
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    _supabase_client = create_client(url, key)
    logger.info("Supabase client initialised")
    return _supabase_client


def get_supabase_client() -> Client:
    """Public accessor for the Supabase client singleton."""
    return _get_sb()


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _serialize_value(value: Any) -> Any:
    """Convert Python values to JSON-compatible types for Supabase/PostgREST."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def _extract_missing_column_from_error(error: Exception) -> str | None:
    """Extract missing column name from PostgREST schema cache errors."""
    payload = error.args[0] if getattr(error, "args", None) else None
    if isinstance(payload, dict) and payload.get("code") == "PGRST204":
        message = payload.get("message") or ""
    else:
        message = str(error)

    match = re.search(r"Could not find the '([^']+)' column", message)
    if not match:
        return None
    return match.group(1)


# ── Query builder classes ────────────────────────────────────────────────────


class _NegationProxy:
    """Handles ``.not_.is_(col, val)`` pattern."""

    def __init__(self, builder: QueryBuilder):
        self._builder = builder

    def is_(self, column: str, value: str) -> QueryBuilder:
        self._builder._negations.append((column, value))
        return self._builder


class QueryBuilder:
    """Chainable query builder that wraps the Supabase Python client."""

    def __init__(self, table: str):
        self._table = table
        self._operation: str = "select"
        self._columns: str = "*"
        self._count_mode: str | None = None
        self._filters: list[tuple[str, str, Any]] = []
        self._or_exprs: list[str] = []
        self._negations: list[tuple[str, str]] = []
        self._order_clauses: list[tuple[str, bool]] = []
        self._limit_val: int | None = None
        self._range_start: int | None = None
        self._range_end: int | None = None
        self._single: bool = False
        self._maybe_single: bool = False
        self._insert_data: dict | list | None = None
        self._update_data: dict | None = None
        self._upsert_data: dict | list | None = None

    # ── SELECT ────────────────────────────────────────────────────────────

    def select(self, columns: str = "*", *, count: str | None = None) -> QueryBuilder:
        self._operation = "select"
        self._columns = columns
        self._count_mode = count
        return self

    # ── MUTATIONS ─────────────────────────────────────────────────────────

    def insert(self, data: dict | list) -> QueryBuilder:
        self._operation = "insert"
        self._insert_data = data
        return self

    def update(self, data: dict) -> QueryBuilder:
        self._operation = "update"
        self._update_data = data
        return self

    def upsert(self, data: dict | list) -> QueryBuilder:
        self._operation = "upsert"
        self._upsert_data = data
        return self

    def delete(self) -> QueryBuilder:
        self._operation = "delete"
        return self

    # ── FILTERS ───────────────────────────────────────────────────────────

    def eq(self, column: str, value: Any) -> QueryBuilder:
        self._filters.append((column, "eq", value))
        return self

    def neq(self, column: str, value: Any) -> QueryBuilder:
        self._filters.append((column, "neq", value))
        return self

    def gt(self, column: str, value: Any) -> QueryBuilder:
        self._filters.append((column, "gt", value))
        return self

    def gte(self, column: str, value: Any) -> QueryBuilder:
        self._filters.append((column, "gte", value))
        return self

    def lt(self, column: str, value: Any) -> QueryBuilder:
        self._filters.append((column, "lt", value))
        return self

    def lte(self, column: str, value: Any) -> QueryBuilder:
        self._filters.append((column, "lte", value))
        return self

    def in_(self, column: str, values: list) -> QueryBuilder:
        if not values:
            self._filters.append(("id", "eq", "__never_match__"))
            return self
        self._filters.append((column, "in_", values))
        return self

    def is_(self, column: str, value: str) -> QueryBuilder:
        self._filters.append((column, "is_", value))
        return self

    def ilike(self, column: str, pattern: str) -> QueryBuilder:
        self._filters.append((column, "ilike", pattern))
        return self

    def like(self, column: str, pattern: str) -> QueryBuilder:
        self._filters.append((column, "like", pattern))
        return self

    def or_(self, filter_expr: str) -> QueryBuilder:
        self._or_exprs.append(filter_expr)
        return self

    @property
    def not_(self) -> _NegationProxy:
        return _NegationProxy(self)

    # ── ORDERING / PAGINATION ─────────────────────────────────────────────

    def order(self, column: str, *, desc: bool = False) -> QueryBuilder:
        self._order_clauses.append((column, desc))
        return self

    def limit(self, count: int) -> QueryBuilder:
        self._limit_val = count
        return self

    def range(self, start: int, end: int) -> QueryBuilder:
        self._range_start = start
        self._range_end = end
        return self

    # ── ROW TARGETING ─────────────────────────────────────────────────────

    def single(self) -> QueryBuilder:
        self._single = True
        return self

    def maybe_single(self) -> QueryBuilder:
        self._maybe_single = True
        return self

    # ── INTERNAL HELPERS ──────────────────────────────────────────────────

    def _apply_filters(self, query):
        """Apply all accumulated filters to a Supabase query object."""
        for col, op, val in self._filters:
            sv = _serialize_value(val)
            if op == "eq":
                query = query.eq(col, sv)
            elif op == "neq":
                query = query.neq(col, sv)
            elif op == "gt":
                query = query.gt(col, sv)
            elif op == "gte":
                query = query.gte(col, sv)
            elif op == "lt":
                query = query.lt(col, sv)
            elif op == "lte":
                query = query.lte(col, sv)
            elif op == "in_":
                query = query.in_(col, sv)
            elif op == "is_":
                query = query.is_(col, sv)
            elif op == "ilike":
                query = query.ilike(col, sv)
            elif op == "like":
                query = query.like(col, sv)

        for expr in self._or_exprs:
            query = query.or_(expr)

        for col, val in self._negations:
            query = query.not_.is_(col, val)

        return query

    def _apply_modifiers(self, query):
        """Apply ordering, limit, range to a query."""
        for col, descending in self._order_clauses:
            query = query.order(col, desc=descending)

        if self._range_start is not None and self._range_end is not None:
            query = query.range(self._range_start, self._range_end)
        elif self._limit_val is not None:
            query = query.limit(self._limit_val)

        if self._single:
            query = query.single()
        elif self._maybe_single:
            query = query.maybe_single()

        return query

    # ── EXECUTE ───────────────────────────────────────────────────────────

    def execute(self) -> APIResponse:
        """Execute the built query and return an APIResponse.

        No global lock — the Supabase client is thread-safe and each query
        runs as an independent HTTP request through httpx connection pooling.
        """
        try:
            sb = _get_sb()
            tbl = sb.table(self._table)

            if self._operation == "select":
                return self._exec_select(tbl)
            if self._operation == "insert":
                return self._exec_insert(tbl)
            if self._operation == "update":
                return self._exec_update(tbl)
            if self._operation == "upsert":
                return self._exec_upsert(tbl)
            if self._operation == "delete":
                return self._exec_delete(tbl)
            raise ValueError(f"Unknown operation: {self._operation}")
        except Exception as e:
            logger.error("DB query failed [%s on %s]: %s", self._operation, self._table, e)
            raise

    async def async_execute(self) -> APIResponse:
        """Execute the query in a thread pool to avoid blocking the event loop."""
        import asyncio

        return await asyncio.to_thread(self.execute)

    # ── Operation implementations ─────────────────────────────────────────

    def _exec_select(self, tbl) -> APIResponse:
        if self._count_mode == "exact":
            query = tbl.select(self._columns, count="exact")
        else:
            query = tbl.select(self._columns)

        query = self._apply_filters(query)
        query = self._apply_modifiers(query)

        resp = query.execute()
        if resp is None:
            return APIResponse(data=None if self._maybe_single else [])
        count = getattr(resp, "count", None)
        return APIResponse(data=resp.data, count=count)

    def _exec_insert(self, tbl) -> APIResponse:
        items = self._insert_data
        if isinstance(items, dict):
            items = [items]
        if not items:
            return APIResponse(data=[])

        now = datetime.utcnow().isoformat()
        prepared = []
        for item in items:
            doc = {k: _serialize_value(v) for k, v in item.items()}
            doc.setdefault("id", str(uuid.uuid4()))
            doc.setdefault("created_at", now)
            prepared.append(doc)

        resp = self._execute_mutation_with_schema_retry(tbl=tbl, operation="insert", rows=prepared)
        return APIResponse(data=resp.data)

    def _exec_update(self, tbl) -> APIResponse:
        update_data = {k: _serialize_value(v) for k, v in (self._update_data or {}).items()}
        if not update_data:
            return APIResponse(data=[])

        query = tbl.update(update_data)
        query = self._apply_filters(query)
        resp = query.execute()
        return APIResponse(data=resp.data)

    def _exec_upsert(self, tbl) -> APIResponse:
        items = self._upsert_data
        if isinstance(items, dict):
            items = [items]
        if not items:
            return APIResponse(data=[])

        now = datetime.utcnow().isoformat()
        prepared = []
        for item in items:
            doc = {k: _serialize_value(v) for k, v in item.items()}
            doc.setdefault("id", str(uuid.uuid4()))
            doc.setdefault("created_at", now)
            prepared.append(doc)

        resp = self._execute_mutation_with_schema_retry(tbl=tbl, operation="upsert", rows=prepared)
        return APIResponse(data=resp.data)

    def _execute_mutation_with_schema_retry(self, *, tbl, operation: str, rows: list[dict]):
        """Retry insert/upsert by stripping columns missing from PostgREST schema cache."""
        payload = rows
        removed_columns: set[str] = set()

        for _ in range(3):
            try:
                if operation == "insert":
                    return tbl.insert(payload).execute()
                if operation == "upsert":
                    return tbl.upsert(payload).execute()
                raise ValueError(f"Unsupported mutation operation: {operation}")
            except Exception as error:
                missing_column = _extract_missing_column_from_error(error)
                if not missing_column or all(missing_column not in row for row in payload):
                    raise

                payload = [{k: v for k, v in row.items() if k != missing_column} for row in payload]
                removed_columns.add(missing_column)

        if removed_columns:
            logger.warning(
                "Retried %s on %s after removing missing columns: %s",
                operation,
                self._table,
                ", ".join(sorted(removed_columns)),
            )

        if operation == "insert":
            return tbl.insert(payload).execute()
        return tbl.upsert(payload).execute()

    def _exec_delete(self, tbl) -> APIResponse:
        query = tbl.delete()
        query = self._apply_filters(query)
        resp = query.execute()
        return APIResponse(data=resp.data)


# ── RPC builder ──────────────────────────────────────────────────────────────


class RPCBuilder:
    """Handles ``.rpc("fn_name", params).execute()`` pattern."""

    def __init__(self, fn_name: str, params: dict | None = None):
        self._fn = fn_name
        self._params = params or {}

    def execute(self) -> APIResponse:
        if self._fn == "increment_user_impact":
            return self._increment_user_impact()
        try:
            sb = _get_sb()
            resp = sb.rpc(self._fn, self._params).execute()
            return APIResponse(data=resp.data)
        except Exception:
            logger.warning("RPC '%s' not implemented — skipped", self._fn)
            return APIResponse(data=None)

    async def async_execute(self) -> APIResponse:
        """Execute the RPC in a thread pool."""
        import asyncio

        return await asyncio.to_thread(self.execute)

    def _increment_user_impact(self) -> APIResponse:
        sb = _get_sb()
        user_id = str(self._params.get("user_id", ""))
        points = self._params.get("points", 0)
        if not user_id:
            return APIResponse(data=None)
        try:
            resp = sb.rpc(
                "increment_user_impact",
                {
                    "p_user_id": user_id,
                    "p_points": points,
                },
            ).execute()
            return APIResponse(data=resp.data)
        except Exception:
            user_resp = sb.table("users").select("total_impact_points").eq("id", user_id).maybe_single().execute()
            current = (user_resp.data or {}).get("total_impact_points", 0) or 0
            sb.table("users").update({"total_impact_points": current + points}).eq("id", user_id).execute()
            return APIResponse(data={"status": "ok"})


# ── Client class (top-level drop-in) ─────────────────────────────────────────


class DatabaseClient:
    """Supabase database client with chainable query builder.

    Usage is identical to the old code::

        from app.db_client import db
        resp = db.table("users").select("*").eq("id", uid).single().execute()
        print(resp.data)
    """

    def table(self, name: str) -> QueryBuilder:
        return QueryBuilder(name)

    def rpc(self, fn_name: str, params: dict | None = None) -> RPCBuilder:
        return RPCBuilder(fn_name, params)


# Module-level singleton
db = DatabaseClient()
