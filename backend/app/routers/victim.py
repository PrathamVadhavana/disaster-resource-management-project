"""
Victim Resource Requests Router
Full CRUD for victim resource requests + dashboard stats
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime
import json, traceback

from app.database import supabase, supabase_admin
from app.schemas import (
    ResourceRequestCreate,
    ResourceRequestUpdate,
    DashboardStats,
    RequestStatus,
)
from app.services.nlp_service import classify_request, extract_urgency_signals, escalate_priority
router = APIRouter()
security = HTTPBearer()


def _get_victim_id(credentials: HTTPAuthorizationCredentials) -> str:
    """Extract and verify victim user from bearer token"""
    try:
        user = supabase.auth.get_user(credentials.credentials)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


def _serialize_items(items) -> list:
    """Serialize ResourceItem models to clean dicts (no None values)."""
    result = []
    for item in items:
        d = item.model_dump() if hasattr(item, 'model_dump') else (item if isinstance(item, dict) else {})
        result.append({k: v for k, v in d.items() if v is not None})
    return result


def _safe_row(row: dict) -> dict:
    """Ensure a DB row is JSON-serializable and has sensible defaults."""
    row = dict(row)  # copy
    # Ensure items is always a list (PostgREST may return null or string)
    items = row.get("items")
    if items is None:
        row["items"] = []
    elif isinstance(items, str):
        try:
            row["items"] = json.loads(items)
        except (json.JSONDecodeError, TypeError):
            row["items"] = []
    # Ensure attachments is always a list
    attachments = row.get("attachments")
    if attachments is None:
        row["attachments"] = []
    elif isinstance(attachments, str):
        try:
            row["attachments"] = json.loads(attachments)
        except (json.JSONDecodeError, TypeError):
            row["attachments"] = []
    # Convert datetime objects to ISO strings if needed
    for key in ("created_at", "updated_at", "estimated_delivery"):
        val = row.get(key)
        if val is not None and isinstance(val, datetime):
            row[key] = val.isoformat()
    return row


# ──────────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────────
@router.post("/requests", status_code=201)
async def create_resource_request(
    request_data: ResourceRequestCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Create a new resource request for the authenticated victim"""
    victim_id = _get_victim_id(credentials)

    # Process items — derive resource_type and quantity from items list
    items_list = _serialize_items(request_data.items) if request_data.items else []
    if items_list:
        total_qty = sum(i.get("quantity", 1) for i in items_list)
        primary_type = items_list[0]["resource_type"] if len(items_list) == 1 else "Multiple"
    else:
        total_qty = request_data.quantity
        primary_type = request_data.resource_type.value if request_data.resource_type else "Custom"

    # ── NLP Triage: auto-classify description before saving ─────────
    nlp_classification = None
    urgency_signals = []
    final_priority = request_data.priority.value

    if request_data.description:
        try:
            classification = classify_request(
                description=request_data.description,
                user_priority=request_data.priority.value,
                user_resource_type=primary_type,
            )
            nlp_classification = classification.to_dict()
            urgency_signals = classification.urgency_signals

            # Auto-escalate priority if urgency signals warrant it
            if classification.priority_was_escalated:
                final_priority = classification.recommended_priority
                print(f"⚠️  NLP escalated priority: {request_data.priority.value} → {final_priority}")

            # Auto-detect resource type if user didn't specify
            if primary_type == "Custom" and classification.resource_types:
                primary_type = classification.resource_types[0] if len(classification.resource_types) == 1 else "Multiple"

            # Use NLP quantity estimate if user left default
            if total_qty == 1 and classification.estimated_quantity > 1:
                total_qty = classification.estimated_quantity

            print(f"🧠 NLP Classification: types={classification.resource_types}, "
                  f"priority={classification.recommended_priority} (conf={classification.confidence:.2f}), "
                  f"signals={[s['label'] for s in urgency_signals]}")
        except Exception as e:
            print(f"⚠️  NLP classification failed (non-blocking): {e}")

    insert_data = {
        "victim_id": victim_id,
        "resource_type": primary_type,
        "quantity": total_qty,
        "items": items_list,
        "priority": final_priority,
        "status": "pending",
        "attachments": request_data.attachments or [],
    }
    if request_data.description:
        insert_data["description"] = request_data.description
    if request_data.latitude is not None:
        insert_data["latitude"] = request_data.latitude
    if request_data.longitude is not None:
        insert_data["longitude"] = request_data.longitude
    if request_data.address_text:
        insert_data["address_text"] = request_data.address_text

    # Store NLP metadata (columns may not exist yet — handled gracefully)
    if nlp_classification:
        insert_data["nlp_classification"] = nlp_classification
    if urgency_signals:
        insert_data["urgency_signals"] = urgency_signals
    if nlp_classification:
        insert_data["ai_confidence"] = nlp_classification.get("confidence", 0)

    try:
        print(f"📦 INSERT DATA: {json.dumps(insert_data, default=str)}")
        response = (
            supabase_admin.table("resource_requests")
            .insert(insert_data)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create request — no data returned")
        row = _safe_row(response.data[0])
        print(f"✅ CREATED: {row.get('id')}")
        return JSONResponse(content=row, status_code=201)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ CREATE ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        # Try to extract detail from supabase/postgrest exceptions
        detail = str(e)
        if hasattr(e, 'message'):
            detail = e.message
        elif hasattr(e, 'args') and e.args:
            detail = str(e.args[0])
        raise HTTPException(status_code=500, detail=f"Error creating request: {detail}")


# ──────────────────────────────────────────────
# LIST (with filters, search, pagination)
# ──────────────────────────────────────────────
@router.get("/requests")
async def list_resource_requests(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    status: Optional[str] = Query(None, description="Filter by status"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    search: Optional[str] = Query(None, description="Search by request ID or description"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """List resource requests for the authenticated victim with filtering"""
    victim_id = _get_victim_id(credentials)

    try:
        query = (
            supabase_admin.table("resource_requests")
            .select("*", count="exact")
            .eq("victim_id", victim_id)
        )

        if status:
            query = query.eq("status", status)
        if resource_type:
            query = query.eq("resource_type", resource_type)
        if priority:
            query = query.eq("priority", priority)
        if search:
            query = query.or_(f"id.eq.{search},description.ilike.%{search}%")

        ascending = sort_order.lower() == "asc"
        query = query.order(sort_by, desc=not ascending)

        offset = (page - 1) * page_size
        query = query.range(offset, offset + page_size - 1)

        response = query.execute()

        return JSONResponse(content={
            "requests": [_safe_row(r) for r in (response.data or [])],
            "total": response.count or 0,
            "page": page,
            "page_size": page_size,
        })
    except Exception as e:
        print(f"❌ LIST ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching requests: {str(e)}")


# ──────────────────────────────────────────────
# GET SINGLE
# ──────────────────────────────────────────────
@router.get("/requests/{request_id}")
async def get_resource_request(
    request_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get a single resource request by ID"""
    victim_id = _get_victim_id(credentials)

    try:
        response = (
            supabase_admin.table("resource_requests")
            .select("*")
            .eq("id", request_id)
            .eq("victim_id", victim_id)
            .single()
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="Request not found")
        return JSONResponse(content=_safe_row(response.data))
    except HTTPException:
        raise
    except Exception as e:
        if "No rows found" in str(e) or "0 rows" in str(e):
            raise HTTPException(status_code=404, detail="Request not found")
        raise HTTPException(status_code=500, detail=f"Error fetching request: {str(e)}")


# ──────────────────────────────────────────────
# UPDATE (only if status is pending)
# ──────────────────────────────────────────────
@router.put("/requests/{request_id}")
async def update_resource_request(
    request_id: str,
    update_data: ResourceRequestUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Update a resource request (only allowed when status is pending)"""
    victim_id = _get_victim_id(credentials)

    try:
        existing = (
            supabase_admin.table("resource_requests")
            .select("*")
            .eq("id", request_id)
            .eq("victim_id", victim_id)
            .single()
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Request not found")

        if existing.data["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot edit request with status '{existing.data['status']}'. Only pending requests can be edited.",
            )

        # Build update dict (only non-None fields)
        update_dict = {}
        for field, value in update_data.model_dump(exclude_unset=True).items():
            if value is not None:
                if hasattr(value, 'value'):
                    update_dict[field] = value.value
                elif isinstance(value, list) and field == 'items':
                    update_dict[field] = _serialize_items(update_data.items) if update_data.items else value
                else:
                    update_dict[field] = value

        # Re-derive resource_type and quantity from items
        if 'items' in update_dict and update_dict['items']:
            items = update_dict['items']
            update_dict['quantity'] = sum(i.get('quantity', 1) if isinstance(i, dict) else i.quantity for i in items)
            update_dict['resource_type'] = items[0].get('resource_type', 'Custom') if len(items) == 1 else 'Multiple'

        if not update_dict:
            return JSONResponse(content=_safe_row(existing.data))

        response = (
            supabase_admin.table("resource_requests")
            .update(update_dict)
            .eq("id", request_id)
            .eq("victim_id", victim_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to update request")
        return JSONResponse(content=_safe_row(response.data[0]))
    except HTTPException:
        raise
    except Exception as e:
        if "No rows found" in str(e) or "0 rows" in str(e):
            raise HTTPException(status_code=404, detail="Request not found")
        print(f"❌ UPDATE ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating request: {str(e)}")


# ──────────────────────────────────────────────
# DELETE / CANCEL
# ──────────────────────────────────────────────
@router.delete("/requests/{request_id}")
async def delete_resource_request(
    request_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Delete/cancel a resource request"""
    victim_id = _get_victim_id(credentials)

    try:
        existing = (
            supabase_admin.table("resource_requests")
            .select("id, status")
            .eq("id", request_id)
            .eq("victim_id", victim_id)
            .single()
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Request not found")

        current_status = existing.data["status"]

        if current_status == "pending":
            supabase_admin.table("resource_requests").delete().eq("id", request_id).execute()
            return {"message": "Request deleted successfully"}
        elif current_status in ("approved", "assigned", "in_progress"):
            supabase_admin.table("resource_requests").update(
                {"status": "rejected", "rejection_reason": "Cancelled by victim"}
            ).eq("id", request_id).execute()
            return {"message": "Request cancelled successfully"}
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel request with status '{current_status}'",
            )
    except HTTPException:
        raise
    except Exception as e:
        if "No rows found" in str(e) or "0 rows" in str(e):
            raise HTTPException(status_code=404, detail="Request not found")
        raise HTTPException(status_code=500, detail=f"Error deleting request: {str(e)}")


# ──────────────────────────────────────────────
# DASHBOARD STATS
# ──────────────────────────────────────────────
@router.get("/dashboard-stats")
async def get_dashboard_stats(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get aggregated dashboard statistics for the victim"""
    victim_id = _get_victim_id(credentials)

    try:
        response = (
            supabase_admin.table("resource_requests")
            .select("status, resource_type, priority")
            .eq("victim_id", victim_id)
            .execute()
        )

        requests = response.data or []

        stats = {
            "total_requests": len(requests),
            "pending": sum(1 for r in requests if r["status"] == "pending"),
            "approved": sum(1 for r in requests if r["status"] == "approved"),
            "assigned": sum(1 for r in requests if r["status"] == "assigned"),
            "in_progress": sum(1 for r in requests if r["status"] == "in_progress"),
            "completed": sum(1 for r in requests if r["status"] == "completed"),
            "rejected": sum(1 for r in requests if r["status"] == "rejected"),
            "by_type": {},
            "by_priority": {},
        }

        for r in requests:
            t = r["resource_type"]
            stats["by_type"][t] = stats["by_type"].get(t, 0) + 1

        for r in requests:
            p = r["priority"]
            stats["by_priority"][p] = stats["by_priority"].get(p, 0) + 1

        return JSONResponse(content=stats)
    except Exception as e:
        print(f"❌ STATS ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")


# ──────────────────────────────────────────────
# AVAILABLE RESOURCES (from available_resources table)
# ──────────────────────────────────────────────
@router.get("/available-resources")
async def get_available_resources(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    category: Optional[str] = Query(None, description="Filter by category"),
):
    """Get currently available resources that victims can request"""
    _get_victim_id(credentials)  # auth check

    try:
        query = (
            supabase_admin.table("available_resources")
            .select("resource_id, category, resource_type, title, description, total_quantity, claimed_quantity, unit, address_text, status")
            .eq("is_active", True)
            .eq("status", "available")
        )

        if category:
            query = query.eq("category", category)

        response = query.order("category").execute()

        resources = []
        for r in (response.data or []):
            total = r.get("total_quantity", 0) or 0
            claimed = r.get("claimed_quantity", 0) or 0
            remaining = max(0, total - claimed)
            if remaining > 0:
                resources.append({
                    "resource_id": r["resource_id"],
                    "category": r["category"],
                    "resource_type": r["resource_type"],
                    "title": r["title"],
                    "description": r.get("description"),
                    "total_quantity": total,
                    "claimed_quantity": claimed,
                    "remaining_quantity": remaining,
                    "unit": r.get("unit", "units"),
                    "address_text": r.get("address_text"),
                })

        return JSONResponse(content={"resources": resources})
    except Exception as e:
        print(f"❌ AVAILABLE RESOURCES ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching available resources: {str(e)}")

