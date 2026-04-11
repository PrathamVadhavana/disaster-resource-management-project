"""
Victim Resource Requests Router
Full CRUD for victim resource requests + dashboard stats
"""

import json
import traceback
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer

from app.database import db_admin
from app.schemas import (
    ResourceRequestCreate,
    ResourceRequestUpdate,
)
from app.services.disaster_linking_service import auto_link_request
from app.services.event_sourcing_service import emit_request_created
from app.services.nlp_service import (
    classify_request,
)
from app.services.notification_service import (
    get_request_audit_trail,
    notify_all_admins,
)

# DistilBERT-backed NLP priority scoring (lazy-loaded, non-blocking)
try:
    from ml.nlp_service import extract_needs as nlp_extract_needs
    from ml.nlp_service import predict_priority as nlp_predict_priority
except ImportError:
    nlp_predict_priority = None  # type: ignore[assignment]
    nlp_extract_needs = None  # type: ignore[assignment]
from app.dependencies import require_role

router = APIRouter()
security = HTTPBearer()


def _serialize_items(items) -> list:
    """Serialize ResourceItem models to clean dicts (no None values)."""
    result = []
    for item in items:
        d = item.model_dump() if hasattr(item, "model_dump") else (item if isinstance(item, dict) else {})
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
    # Ensure JSONB fields are lists (nlp_classification, urgency_signals, etc.)
    for key in ("nlp_classification", "urgency_signals", "fulfillment_entries", "extracted_needs"):
        val = row.get(key)
        if val is None:
            pass  # leave as None
        elif isinstance(val, str):
            try:
                row[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                row[key] = []
    # Convert ALL datetime objects to ISO strings (database returns datetime)
    for key, val in list(row.items()):
        if isinstance(val, datetime):
            row[key] = val.isoformat()
    return row


# ── Valid resource types matching the DB CHECK constraint ────────────────
VALID_RESOURCE_TYPES = {
    "Food",
    "Water",
    "Medical",
    "Shelter",
    "Clothing",
    "Financial Aid",
    "Evacuation",
    "Volunteers",
    "Custom",
    "Multiple",
}

# Map common DB category variants / display names to valid resource types
CATEGORY_ALIAS = {
    "Clothes": "Clothing",
    "Medical Team": "Medical",
    "Food Supplies": "Food",
    "Shelter Materials": "Shelter",
    "Evacuation Support": "Evacuation",
    "NGO Team": "Volunteers",
    "Financial": "Financial Aid",
    "Finance": "Financial Aid",
    "Rescue": "Evacuation",
}


async def resolve_resource_type(raw_type: str) -> str:
    """Resolve a resource type string to a valid DB enum value.
    If it's already valid, return as-is. Otherwise, check aliases,
    then look it up in the resources table to find the type.
    Falls back to 'Custom'."""
    if raw_type in VALID_RESOURCE_TYPES:
        return raw_type
    mapped = CATEGORY_ALIAS.get(raw_type)
    if mapped:
        return mapped
    # Check if the raw_type *contains* a known type (e.g. "Rice (25 kg bags)" -> Food)
    _TYPE_KEYWORDS = {
        "Food": ["rice", "wheat", "flour", "dal", "grain", "meal", "bread", "food", "ration", "biscuit"],
        "Water": ["water", "aqua", "drink", "purif"],
        "Medical": ["medic", "first aid", "bandage", "medicine", "pharma", "health", "doctor", "nurse", "hospital"],
        "Shelter": ["shelter", "tent", "tarp", "blanket", "mattress", "roof"],
        "Clothing": ["cloth", "garment", "shirt", "trouser", "jacket", "sweater", "shoes"],
        "Evacuation": ["evacu", "rescue", "transport", "vehicle", "boat"],
        "Volunteers": ["volunteer", "helper", "manpower", "team"],
        "Financial Aid": ["money", "cash", "fund", "financial", "donation"],
    }
    lower = raw_type.lower()
    for category, keywords in _TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return category
    # Try to look up the type from resources table by name
    try:
        r_resp = (
            await db_admin.table("resources")
            .select("type")
            .eq("name", raw_type)
            .maybe_single()
            .async_execute()
        )
        if r_resp.data:
            rtype = r_resp.data["type"]
            return (
                CATEGORY_ALIAS.get(rtype, rtype) if rtype in VALID_RESOURCE_TYPES or rtype in CATEGORY_ALIAS else "Custom"
            )
    except Exception:
        pass
    return "Custom"


def resolve_resource_type_sync(raw_type: str) -> str:
    """Synchronous version of resolve_resource_type for simple cases.
    Does NOT do DB lookup — only checks valid types, aliases, and keywords."""
    if raw_type in VALID_RESOURCE_TYPES:
        return raw_type
    mapped = CATEGORY_ALIAS.get(raw_type)
    if mapped:
        return mapped
    _TYPE_KEYWORDS = {
        "Food": ["rice", "wheat", "flour", "dal", "grain", "meal", "bread", "food", "ration", "biscuit"],
        "Water": ["water", "aqua", "drink", "purif"],
        "Medical": ["medic", "first aid", "bandage", "medicine", "pharma", "health"],
        "Shelter": ["shelter", "tent", "tarp", "blanket", "mattress"],
        "Clothing": ["cloth", "garment", "shirt", "trouser", "jacket"],
        "Evacuation": ["evacu", "rescue", "transport", "vehicle"],
        "Volunteers": ["volunteer", "helper", "manpower"],
        "Financial Aid": ["money", "cash", "fund", "financial"],
    }
    lower = raw_type.lower()
    for category, keywords in _TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return category
    return "Custom"


# ──────────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────────
@router.post("/requests", status_code=201)
async def create_resource_request(
    request_data: ResourceRequestCreate,
    user: dict = Depends(require_role("victim", "admin")),
):
    """Create a new resource request for the authenticated victim"""
    victim_id = user["id"]

    # (VALID_RESOURCE_TYPES and resolve_resource_type are now module-level)

    # Process items — derive resource_type and quantity from items list
    items_list = _serialize_items(request_data.items) if request_data.items else []
    if items_list:
        total_qty = sum(i.get("quantity", 1) for i in items_list)
        raw_type = items_list[0]["resource_type"] if len(items_list) == 1 else "Multiple"
        primary_type = await resolve_resource_type(raw_type)
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
                primary_type = (
                    classification.resource_types[0] if len(classification.resource_types) == 1 else "Multiple"
                )

            # Use NLP quantity estimate if user left default
            if total_qty == 1 and classification.estimated_quantity > 1:
                total_qty = classification.estimated_quantity

            print(
                f"🧠 NLP Classification: types={classification.resource_types}, "
                f"priority={classification.recommended_priority} (conf={classification.confidence:.2f}), "
                f"signals={[s['label'] for s in urgency_signals]}"
            )
        except Exception as e:
            print(f"⚠️  NLP classification failed (non-blocking): {e}")

    insert_data = {
        "victim_id": victim_id,
        "resource_type": primary_type,
        "quantity": total_qty,
        "items": items_list,
        "priority": final_priority,
        "status": "pending",
        "assigned_to": None,
        "attachments": request_data.attachments or [],
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if request_data.description:
        insert_data["description"] = request_data.description
    if request_data.latitude is not None:
        insert_data["latitude"] = request_data.latitude
    if request_data.longitude is not None:
        insert_data["longitude"] = request_data.longitude
    if request_data.address_text:
        insert_data["address_text"] = request_data.address_text

    # Fall back to victim's stored location if no GPS provided
    if insert_data.get("latitude") is None or insert_data.get("longitude") is None:
        try:
            victim_user = (
                await db_admin.table("users").select("metadata").eq("id", victim_id).maybe_single().async_execute()
            )
            meta = (victim_user.data or {}).get("metadata") or {}
            if meta.get("latitude") and meta.get("longitude"):
                if insert_data.get("latitude") is None:
                    insert_data["latitude"] = meta["latitude"]
                if insert_data.get("longitude") is None:
                    insert_data["longitude"] = meta["longitude"]
                if not insert_data.get("address_text"):
                    insert_data["address_text"] = meta.get("address") or None
                print(f"📍 Using victim stored GPS: {meta['latitude']}, {meta['longitude']}")
        except Exception as e:
            print(f"⚠️  Failed to fetch victim location fallback: {e}")

    # Store NLP metadata (columns may not exist yet — handled gracefully)
    if nlp_classification:
        insert_data["nlp_classification"] = nlp_classification
    if urgency_signals:
        insert_data["urgency_signals"] = urgency_signals
    if nlp_classification:
        insert_data["ai_confidence"] = nlp_classification.get("confidence", 0)

    # ── DistilBERT NLP priority scoring ────────────────────────────
    # Run the fine-tuned model (if available) for a second opinion on
    # priority.  When confidence > 0.85 the model overrides the manual
    # priority.  Both values are persisted so reviewers can compare.
    nlp_priority_result = None
    extracted_needs_list = None
    manual_priority = request_data.priority.value  # preserve original

    if request_data.description:
        try:
            if nlp_predict_priority is not None:
                nlp_priority_result = nlp_predict_priority(request_data.description)
                insert_data["nlp_priority"] = nlp_priority_result["predicted_priority"]
                insert_data["nlp_confidence"] = nlp_priority_result["confidence"]

                # Override priority when model is highly confident
                if nlp_priority_result["confidence"] > 0.85:
                    final_priority = nlp_priority_result["predicted_priority"]
                    insert_data["priority"] = final_priority
                    print(
                        f"🤖 DistilBERT override: "
                        f"{manual_priority} → {final_priority} "
                        f"(conf={nlp_priority_result['confidence']:.3f})"
                    )
        except Exception as e:
            print(f"⚠️  DistilBERT priority prediction failed (non-blocking): {e}")

        try:
            if nlp_extract_needs is not None:
                extracted_needs_list = nlp_extract_needs(request_data.description)
                if extracted_needs_list:
                    insert_data["extracted_needs"] = extracted_needs_list
        except Exception as e:
            print(f"⚠️  NLP needs extraction failed (non-blocking): {e}")

    # Always store the manual priority for audit
    insert_data["manual_priority"] = manual_priority

    # Determine disaster type (explicit from form or auto-detected from description)
    effective_disaster_type = request_data.disaster_type
    if not effective_disaster_type and classification:
        effective_disaster_type = classification.disaster_type
        if effective_disaster_type:
            print(f"🤖 NLP auto-detected disaster type: {effective_disaster_type}")

    # ── Auto-create Disaster from Report ───────────────────────────
    # If the victim specifies the kind of disaster, we create a new
    # disaster record and link it. This ensures it shows up in the
    # admin dashboard as a victim-created entry.
    print(f"🔍 Checking for effective_disaster_type: '{effective_disaster_type}' (original: '{request_data.disaster_type}')")
    if effective_disaster_type:
        try:
            print(f"🆕 Attempting to auto-create disaster: {effective_disaster_type}")
            # Check for a default location ID
            try:
                loc_resp = await db_admin.table("locations").select("id").limit(1).async_execute()
                default_loc_id = loc_resp.data[0]["id"] if loc_resp.data else "sandbox"
            except Exception as loc_err:
                print(f"⚠️  Location fetch failed: {loc_err}")
                default_loc_id = "sandbox"
            
            print(f"📍 Using location_id: {default_loc_id}")

            disaster_payload = {
                "title": f"Reported {effective_disaster_type.capitalize()} near {request_data.address_text or 'Victim Location'}",
                "type": effective_disaster_type,
                "severity": "medium",
                "description": f"Victim reported: {request_data.description or 'No details provided'}",
                "status": "active",
                "start_date": datetime.now(UTC).isoformat(),
                "latitude": insert_data.get("latitude"),
                "longitude": insert_data.get("longitude"),
                "location_name": insert_data.get("address_text"),
                "location_id": default_loc_id,
                "metadata": {
                    "source": "victim",
                    "reported_by": victim_id,
                    "auto_created": True
                }
            }
            d_resp = await db_admin.table("disasters").insert(disaster_payload).async_execute()
            print(f"📡 DB Insert Response: {d_resp.data}")
            if d_resp.data:
                linked_id = d_resp.data[0]["id"]
                insert_data["linked_disaster_id"] = linked_id
                print(f"✅ Auto-created disaster for victim report: {linked_id}")
            else:
                print("❌ DB Insert returned no data (silent failure?)")
        except Exception as e:
            print(f"⚠️  Auto-disaster creation failed: {e}")
            traceback.print_exc()

    try:
        print(f"📦 INSERT DATA: {json.dumps(insert_data, default=str)}")
        response = await db_admin.table("resource_requests").insert(insert_data).async_execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create request — no data returned")
        row = _safe_row(response.data[0])
        print(f"✅ CREATED: {row.get('id')}")

        # ── Notify all admins about the new request ─────────
        try:
            await notify_all_admins(
                title="📋 New Victim Request",
                message=f"New {final_priority} priority request for {primary_type} from victim.",
                notification_type="warning" if final_priority in ("critical", "high") else "info",
                related_id=row.get("id"),
                related_type="request",
            )
        except Exception as ne:
            print(f"⚠️  Admin notification failed (non-blocking): {ne}")

        # ── Auto-link to nearest active disaster ─────────
        try:
            link_result = await auto_link_request(row)
            if link_result:
                row["linked_disaster_id"] = link_result.get("disaster_id")
                print(
                    f"🌍 Auto-linked to disaster: {link_result.get('disaster_name')} ({link_result.get('distance_km')}km)"
                )
        except Exception as le:
            print(f"⚠️  Disaster auto-link failed (non-blocking): {le}")

        # ── Emit event sourcing event ─────────
        try:
            await emit_request_created(
                request_id=row.get("id"),
                victim_id=victim_id,
                request_data={
                    "resource_type": primary_type,
                    "priority": final_priority,
                    "quantity": total_qty,
                },
            )
        except Exception as ee:
            print(f"⚠️  Event sourcing emit failed (non-blocking): {ee}")

        return JSONResponse(content=row, status_code=201)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ CREATE ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        # Try to extract detail from database exceptions
        detail = str(e)
        if hasattr(e, "message"):
            detail = e.message
        elif hasattr(e, "args") and e.args:
            detail = str(e.args[0])
        raise HTTPException(status_code=500, detail=f"Error creating request: {detail}")


# ──────────────────────────────────────────────
# LIST (with filters, search, pagination)
# ──────────────────────────────────────────────
@router.get("/requests")
async def list_resource_requests(
    user: dict = Depends(require_role("victim", "admin", "volunteer", "donor", "ngo")),
    status: str | None = Query(None, description="Filter by status"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    priority: str | None = Query(None, description="Filter by priority"),
    search: str | None = Query(None, description="Search by request ID or description"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """List resource requests. Victims see own; Volunteers see all unverified or their own verified; Admins see all."""
    user_id = user["id"]
    role = user.get("role")

    try:
        query = db_admin.table("resource_requests").select("*", count="exact")

        # ── Role-Based Filtering ──
        if role == "victim":
            query = query.eq("victim_id", user_id)
        elif role == "volunteer":
            # Volunteers see:
            # 1. Unverified requests
            # 2. Requests verified by them
            query = query.or_(f"is_verified.is.null,is_verified.eq.false,verified_by.eq.{user_id}")
        elif role == "ngo":
            # NGOs see requests assigned to them + approved requests they can claim
            query = query.or_(f"assigned_to.eq.{user_id},status.eq.approved,status.eq.under_review")
        elif role == "donor":
            # Donors see approved/partially fulfilled requests they can contribute to
            query = query.in_("status", ["approved", "under_review", "assigned"])
        # Admins see everything (no filter)

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

        response = await query.async_execute()
        base_requests = response.data or []

        # Manual enrichment for assigned_user
        assigned_ids = [r["assigned_to"] for r in base_requests if r.get("assigned_to")]
        user_map = {}
        if assigned_ids:
            u_resp = (
                await db_admin.table("users").select("id, full_name, metadata").in_("id", assigned_ids).async_execute()
            )
            for u in u_resp.data or []:
                user_map[u["id"]] = u

        # Map back to requests
        final_requests = []
        for r in base_requests:
            row = _safe_row(r)
            aid = row.get("assigned_to")
            if aid:
                row["assigned_user"] = user_map.get(aid)
            final_requests.append(row)

        return {
            "requests": final_requests,
            "total": response.count or 0,
            "page": page,
            "page_size": page_size,
        }
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
    user: dict = Depends(require_role("victim", "admin", "ngo", "volunteer")),
):
    """Get a single resource request by ID"""
    user_id = user["id"]
    role = user.get("role")

    try:
        query = db_admin.table("resource_requests").select("*").eq("id", request_id)

        if role == "victim":
            query = query.eq("victim_id", user_id)
        # Admins, NGOs, and Volunteers can see the specific request if they have the ID

        response = await query.single().async_execute()

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
# TIMELINE / AUDIT TRAIL
# ──────────────────────────────────────────────
@router.get("/requests/{request_id}/timeline")
async def get_request_timeline(
    request_id: str,
    user: dict = Depends(require_role("victim", "admin", "ngo")),
):
    """Get the timeline (audit trail) for a specific resource request."""
    victim_id = user["id"]

    # First, verify ownership if the user is a victim
    if user["role"] == "victim":
        resp = (
            await db_admin.table("resource_requests")
            .select("id")
            .eq("id", request_id)
            .eq("victim_id", victim_id)
            .maybe_single()
            .async_execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Request not found or not authorized")

    trail = await get_request_audit_trail(request_id)
    return JSONResponse(content={"timeline": trail})


# ──────────────────────────────────────────────
# UPDATE (only if status is pending)
# ──────────────────────────────────────────────
@router.put("/requests/{request_id}")
async def update_resource_request(
    request_id: str,
    update_data: ResourceRequestUpdate,
    user: dict = Depends(require_role("victim", "admin")),
):
    """Update a resource request (only allowed when status is pending)"""
    victim_id = user["id"]

    try:
        existing = (
            await db_admin.table("resource_requests")
            .select("*")
            .eq("id", request_id)
            .eq("victim_id", victim_id)
            .single()
            .async_execute()
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
                if hasattr(value, "value"):
                    update_dict[field] = value.value
                elif isinstance(value, list) and field == "items":
                    update_dict[field] = _serialize_items(update_data.items) if update_data.items else value
                else:
                    update_dict[field] = value

        # Re-derive resource_type and quantity from items
        if "items" in update_dict and update_dict["items"]:
            items = update_dict["items"]
            update_dict["quantity"] = sum(i.get("quantity", 1) if isinstance(i, dict) else i.quantity for i in items)
            raw_rt = items[0].get("resource_type", "Custom") if len(items) == 1 else "Multiple"
            update_dict["resource_type"] = await resolve_resource_type(raw_rt)

        if not update_dict:
            return JSONResponse(content=_safe_row(existing.data))

        response = (
            await db_admin.table("resource_requests")
            .update(update_dict)
            .eq("id", request_id)
            .eq("victim_id", victim_id)
            .async_execute()
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
    user: dict = Depends(require_role("victim", "admin")),
):
    """Delete/cancel a resource request"""
    victim_id = user["id"]

    try:
        existing = (
            await db_admin.table("resource_requests")
            .select("id, status")
            .eq("id", request_id)
            .eq("victim_id", victim_id)
            .single()
            .async_execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Request not found")

        current_status = existing.data["status"]

        if current_status == "pending":
            await db_admin.table("resource_requests").delete().eq("id", request_id).async_execute()
            return {"message": "Request deleted successfully"}
        elif current_status in ("approved", "assigned", "in_progress", "under_review", "availability_submitted"):
            await (
                db_admin.table("resource_requests")
                .update({"status": "rejected", "rejection_reason": "Cancelled by victim"})
                .eq("id", request_id)
                .async_execute()
            )
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
    user: dict = Depends(require_role("victim", "admin")),
):
    """Get aggregated dashboard statistics for the victim"""
    victim_id = user["id"]

    try:
        response = (
            await db_admin.table("resource_requests")
            .select("status, resource_type, priority")
            .eq("victim_id", victim_id)
            .async_execute()
        )

        requests = response.data or []

        stats = {
            "total_requests": len(requests),
            "pending": sum(1 for r in requests if r["status"] == "pending"),
            "approved": sum(1 for r in requests if r["status"] == "approved"),
            "under_review": sum(1 for r in requests if r["status"] == "under_review"),
            "assigned": sum(1 for r in requests if r["status"] == "assigned"),
            "in_progress": sum(1 for r in requests if r["status"] == "in_progress"),
            "delivered": sum(1 for r in requests if r["status"] == "delivered"),
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
# AVAILABLE RESOURCES (from resources table)
# ──────────────────────────────────────────────
@router.get("/available-resources")
async def get_available_resources(
    user: dict = Depends(require_role("victim", "admin")),
    category: str | None = Query(None, description="Filter by resource type"),
):
    """Get currently available resources that victims can request"""

    try:
        query = (
            db_admin.table("resources")
            .select("id, type, name, quantity, unit, status, description")
            .eq("status", "available")
        )

        if category:
            query = query.eq("type", category)

        response = await query.order("type").limit(500).async_execute()

        resources = []
        for r in response.data or []:
            qty = r.get("quantity", 0) or 0
            if qty > 0:
                resources.append(
                    {
                        "resource_id": r["id"],
                        "category": r["type"],
                        "resource_type": r["type"],
                        "title": r["name"],
                        "description": r.get("description"),
                        "total_quantity": qty,
                        "claimed_quantity": 0,
                        "remaining_quantity": qty,
                        "unit": r.get("unit", "units"),
                    }
                )

        return JSONResponse(content={"resources": resources})
    except Exception as e:
        print(f"❌ AVAILABLE RESOURCES ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching available resources: {str(e)}")


# ──────────────────────────────────────────────
# FULFILLMENT TRACKING
# ──────────────────────────────────────────────
@router.get("/requests/{request_id}/fulfillment")
async def get_request_fulfillment(
    request_id: str,
    user: dict = Depends(require_role("victim", "admin", "ngo", "donor")),
):
    """Get fulfillment progress for a specific request — shows which NGOs/donors are contributing."""
    try:
        query = (
            db_admin.table("resource_requests")
            .select("id, items, quantity, resource_type, status, fulfillment_entries, fulfillment_pct")
            .eq("id", request_id)
        )

        if user["role"] == "victim":
            query = query.eq("victim_id", user["id"])

        resp = await query.single().async_execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Request not found")

        request_data = resp.data
        fulfillment_entries = request_data.get("fulfillment_entries") or []
        items = request_data.get("items") or []

        # Compute per-item fulfillment breakdown
        item_fulfillment = {}
        for it in items:
            rt = it.get("resource_type", "Custom")
            item_fulfillment[rt] = {
                "requested": it.get("quantity", 1),
                "fulfilled": 0,
                "providers": [],
            }

        for entry in fulfillment_entries:
            for ri in entry.get("resource_items") or []:
                rt = ri.get("resource_type", "Custom")
                if rt not in item_fulfillment:
                    item_fulfillment[rt] = {"requested": 0, "fulfilled": 0, "providers": []}
                item_fulfillment[rt]["fulfilled"] += ri.get("quantity", 0)
                item_fulfillment[rt]["providers"].append(
                    {
                        "name": entry.get("provider_name", "Anonymous"),
                        "role": entry.get("provider_role", "unknown"),
                        "quantity": ri.get("quantity", 0),
                        "status": entry.get("status", "pledged"),
                        "created_at": entry.get("created_at"),
                    }
                )

        return {
            "request_id": request_id,
            "status": request_data.get("status"),
            "fulfillment_pct": request_data.get("fulfillment_pct", 0),
            "total_requested": request_data.get("quantity", 1),
            "item_fulfillment": item_fulfillment,
            "entries": fulfillment_entries,
        }
    except HTTPException:
        raise
    except Exception as e:
        if "No rows found" in str(e) or "0 rows" in str(e):
            raise HTTPException(status_code=404, detail="Request not found")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ──────────────────────────────────────────────
# RESOURCE POOLING
# ──────────────────────────────────────────────
@router.get("/requests/{request_id}/resource-pool")
async def get_resource_pool(
    request_id: str,
    user: dict = Depends(require_role("victim", "admin", "ngo", "donor")),
):
    """Get the resource pool for a request — shows all contributors grouped by role,
    supporting NGO-NGO, donor-donor, and NGO-donor collaborative fulfillment."""
    try:
        query = (
            db_admin.table("resource_requests")
            .select("id, items, quantity, resource_type, status, fulfillment_entries, fulfillment_pct, disaster_id")
            .eq("id", request_id)
        )

        if user["role"] == "victim":
            query = query.eq("victim_id", user["id"])

        resp = await query.single().async_execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Request not found")

        request_data = resp.data
        fulfillment_entries = request_data.get("fulfillment_entries") or []
        items = request_data.get("items") or []
        total_requested = sum(it.get("quantity", 1) for it in items) if items else request_data.get("quantity", 1)

        # Group contributors by role
        ngo_contributors = []
        donor_contributors = []
        for entry in fulfillment_entries:
            contributor = {
                "provider_id": entry.get("provider_id"),
                "provider_name": entry.get("provider_name", "Anonymous"),
                "donation_type": entry.get("donation_type", "resource"),
                "amount": entry.get("amount", 0),
                "resource_items": entry.get("resource_items") or [],
                "status": entry.get("status", "pledged"),
                "created_at": entry.get("created_at"),
                "estimated_delivery_time": entry.get("estimated_delivery_time"),
                "distance_km": entry.get("distance_km"),
            }
            role = entry.get("provider_role", "unknown")
            if role == "ngo":
                ngo_contributors.append(contributor)
            elif role == "donor":
                donor_contributors.append(contributor)

        # Calculate per-item pool breakdown
        item_pool = {}
        for it in items:
            rt = it.get("resource_type", "Custom")
            item_pool[rt] = {
                "requested": it.get("quantity", 1),
                "fulfilled_by_ngo": 0,
                "fulfilled_by_donor": 0,
                "total_fulfilled": 0,
                "gap": it.get("quantity", 1),
            }

        total_money = 0
        for entry in fulfillment_entries:
            role = entry.get("provider_role", "unknown")
            for ri in entry.get("resource_items") or []:
                rt = ri.get("resource_type", "Custom")
                qty = ri.get("quantity", 0)
                if rt not in item_pool:
                    item_pool[rt] = {
                        "requested": 0,
                        "fulfilled_by_ngo": 0,
                        "fulfilled_by_donor": 0,
                        "total_fulfilled": 0,
                        "gap": 0,
                    }
                if role == "ngo":
                    item_pool[rt]["fulfilled_by_ngo"] += qty
                elif role == "donor":
                    item_pool[rt]["fulfilled_by_donor"] += qty
                item_pool[rt]["total_fulfilled"] += qty
            if entry.get("donation_type") in ("money", "both") and entry.get("amount", 0) > 0:
                total_money += entry.get("amount", 0)

        for rt in item_pool:
            item_pool[rt]["gap"] = max(0, item_pool[rt]["requested"] - item_pool[rt]["total_fulfilled"])

        # Determine pool type
        has_ngo = len(ngo_contributors) > 0
        has_donor = len(donor_contributors) > 0
        if has_ngo and has_donor:
            pool_type = "ngo_donor"
        elif has_ngo and len(ngo_contributors) > 1:
            pool_type = "ngo_ngo"
        elif has_donor and len(donor_contributors) > 1:
            pool_type = "donor_donor"
        elif has_ngo:
            pool_type = "single_ngo"
        elif has_donor:
            pool_type = "single_donor"
        else:
            pool_type = "none"

        return {
            "request_id": request_id,
            "status": request_data.get("status"),
            "fulfillment_pct": request_data.get("fulfillment_pct", 0),
            "total_requested": total_requested,
            "total_money": total_money,
            "pool_type": pool_type,
            "total_contributors": len(ngo_contributors) + len(donor_contributors),
            "ngo_contributors": ngo_contributors,
            "donor_contributors": donor_contributors,
            "item_pool": item_pool,
        }
    except HTTPException:
        raise
    except Exception as e:
        if "No rows found" in str(e) or "0 rows" in str(e):
            raise HTTPException(status_code=404, detail="Request not found")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
