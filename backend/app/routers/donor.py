"""
Donor endpoints – donations CRUD, pledge support, and donor stats.

All endpoints require a valid Bearer token. Users can only manage their
own donations/pledges (RLS enforced at DB level).
"""

import io
import math
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.database import db_admin
from app.dependencies import get_current_user_id, require_donor, require_verified_donor
from app.services.notification_service import notify_user

router = APIRouter()


# ── GPS Utility ───────────────────────────────────────────────────────────────


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two GPS points in km."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _send_notification(user_id: str, title: str, message: str, priority: str = "medium", data: dict = None):
    """Insert into the notifications table."""
    try:
        await (
            db_admin.table("notifications")
            .insert(
                {
                    "user_id": user_id,
                    "title": title,
                    "message": message,
                    "priority": priority,
                    "data": data or {},
                }
            )
            .async_execute()
        )
    except Exception as e:
        print(f"Notification insert error: {e}")


async def _log_pulse(
    actor_id: str,
    target_id: str,
    action_type: str,
    description: str,
    metadata: dict = None,
):
    """Write to operational_pulse for audit trail."""
    try:
        await (
            db_admin.table("operational_pulse")
            .insert(
                {
                    "actor_id": actor_id,
                    "target_id": target_id,
                    "action_type": action_type,
                    "description": description,
                    "metadata": metadata or {},
                }
            )
            .async_execute()
        )
    except Exception as e:
        print(f"Pulse log error: {e}")


# ── Schemas ───────────────────────────────────────────────────────────────────


class DonationCreate(BaseModel):
    disaster_id: str | None = None
    request_id: str | None = None
    amount: float = 0
    currency: str = "USD"
    status: str = "pending"
    payment_ref: str | None = None
    notes: str | None = None
    # Resource donation fields (donor can donate money AND/OR resources)
    donation_type: str = "money"  # "money", "resource", "both"
    resource_items: list | None = None  # [{"resource_type": "Water", "quantity": 10, "unit": "bottles"}]


class DonationUpdate(BaseModel):
    amount: float | None = None
    status: str | None = None
    request_id: str | None = None
    payment_ref: str | None = None
    notes: str | None = None
    donation_type: str | None = None
    resource_items: list | None = None


class PledgeCreate(BaseModel):
    disaster_id: str


# ── Approved Requests (for donor browsing) ────────────────────────────────────


@router.get("/approved-requests")
async def list_approved_requests(
    resource_type: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    donor_latitude: float | None = Query(None, description="Donor GPS latitude"),
    donor_longitude: float | None = Query(None, description="Donor GPS longitude"),
    sort: str | None = Query("priority", description="Sort: priority, distance, created_at"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    donor=Depends(require_donor),
):
    """List approved resource requests that donors can pledge support for.
    Supports distance-based sorting when GPS coordinates are provided."""
    import json

    try:
        # Resolve donor GPS early so we know if distance sorting is needed
        donor_id = donor.get("id")
        d_lat = donor_latitude
        d_lon = donor_longitude
        if d_lat is None or d_lon is None:
            try:
                du = await db_admin.table("users").select("metadata").eq("id", donor_id).maybe_single().async_execute()
                if du.data and du.data.get("metadata"):
                    d_lat = d_lat or du.data["metadata"].get("latitude")
                    d_lon = d_lon or du.data["metadata"].get("longitude")
            except Exception:
                pass

        # Store donor GPS in metadata for future use
        if donor_latitude and donor_longitude:
            try:
                cur = await db_admin.table("users").select("metadata").eq("id", donor_id).maybe_single().async_execute()
                meta = (cur.data or {}).get("metadata") or {}
                meta["latitude"] = donor_latitude
                meta["longitude"] = donor_longitude
                await db_admin.table("users").update({"metadata": meta}).eq("id", donor_id).async_execute()
            except Exception:
                pass

        _PRIO_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        query = db_admin.table("resource_requests").select("*", count="exact")
        query = query.in_("status", ["approved", "assigned", "availability_submitted", "under_review"])

        if resource_type:
            query = query.eq("resource_type", resource_type)
        if priority:
            query = query.eq("priority", priority)
        if search:
            query = query.or_(f"description.ilike.%{search}%,resource_type.ilike.%{search}%")

        # Always fetch all and sort client-side for correct priority/distance ordering
        query = query.order("created_at", desc=True)

        response = await query.async_execute()
        base_requests = response.data or []
        total_count = response.count or 0

        # Enrich with victim info
        victim_ids = list(set(r["victim_id"] for r in base_requests if r.get("victim_id")))
        user_map = {}
        if victim_ids:
            users_resp = await db_admin.table("users").select("id, full_name").in_("id", victim_ids).async_execute()
            for u in users_resp.data or []:
                user_map[u["id"]] = u

        # Check which requests this donor has already pledged to
        existing_donations = []
        if donor_id and base_requests:
            req_ids = [r["id"] for r in base_requests]
            d_resp = (
                await db_admin.table("donations")
                .select("request_id")
                .eq("user_id", donor_id)
                .in_("request_id", req_ids)
                .async_execute()
            )
            existing_donations = [d["request_id"] for d in (d_resp.data or [])]

        requests = []
        for r in base_requests:
            row = dict(r)
            for key in (
                "items",
                "attachments",
                "nlp_classification",
                "urgency_signals",
            ):
                val = row.get(key)
                if val is None:
                    row[key] = []
                elif isinstance(val, str):
                    try:
                        row[key] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        row[key] = []

            vid = row.get("victim_id")
            v = user_map.get(vid, {})
            row["victim_name"] = v.get("full_name") or "Anonymous"
            row["already_pledged"] = row["id"] in existing_donations

            # Compute distance
            row["distance_km"] = None
            if d_lat and d_lon and row.get("latitude") and row.get("longitude"):
                row["distance_km"] = round(haversine_km(d_lat, d_lon, row["latitude"], row["longitude"]), 2)

            requests.append(row)

        # Sort client-side for correct ordering
        if sort == "distance" and d_lat and d_lon:
            requests.sort(key=lambda r: r["distance_km"] if r["distance_km"] is not None else float("inf"))
        else:
            # Default: sort by priority (critical first), then created_at descending
            requests.sort(
                key=lambda r: (
                    _PRIO_ORDER.get(r.get("priority", "low"), 99),
                    -(datetime.fromisoformat(r["created_at"]).timestamp() if r.get("created_at") else 0),
                )
            )
        # Apply pagination after sorting
        offset = (page - 1) * page_size
        requests = requests[offset : offset + page_size]

        return {
            "requests": requests,
            "total": total_count,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        print(f"\u274c DONOR APPROVED REQUESTS ERROR: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching approved requests: {str(e)}")


@router.get("/requests/{request_id}/pool")
async def get_request_pool_donor(request_id: str, donor=Depends(require_donor)):
    """View resource pool for a request — shows all NGO and donor contributors."""
    resp = (
        await db_admin.table("resource_requests")
        .select("id, items, quantity, resource_type, status, fulfillment_entries, fulfillment_pct")
        .eq("id", request_id)
        .in_(
            "status",
            ["approved", "assigned", "availability_submitted", "under_review", "in_progress", "delivered", "completed"],
        )
        .single()
        .async_execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Request not found")

    entries = resp.data.get("fulfillment_entries") or []
    items = resp.data.get("items") or []

    ngo_list, donor_list = [], []
    for e in entries:
        info = {
            "provider_name": e.get("provider_name", "Anonymous"),
            "donation_type": e.get("donation_type", "resource"),
            "amount": e.get("amount", 0),
            "resource_items": e.get("resource_items") or [],
            "status": e.get("status", "pledged"),
            "created_at": e.get("created_at"),
        }
        if e.get("provider_role") == "ngo":
            ngo_list.append(info)
        else:
            donor_list.append(info)

    total_requested = sum(it.get("quantity", 1) for it in items) if items else resp.data.get("quantity", 1)
    return {
        "request_id": request_id,
        "fulfillment_pct": resp.data.get("fulfillment_pct", 0),
        "total_requested": total_requested,
        "total_contributors": len(entries),
        "ngo_contributors": ngo_list,
        "donor_contributors": donor_list,
    }


# ── Donation Endpoints ────────────────────────────────────────────────────────


@router.get("/donations")
async def list_donations(
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
):
    """List all donations for the authenticated donor."""
    q = db_admin.table("donations").select("*", count="exact").eq("user_id", user_id).order("created_at", desc=True)
    if status:
        q = q.eq("status", status)

    offset = (page - 1) * page_size
    q = q.range(offset, offset + page_size - 1)
    resp = await q.async_execute()
    base_donations = resp.data or []
    total_count = resp.count or 0

    if not base_donations:
        return {
            "donations": [],
            "total": total_count,
            "page": page,
            "page_size": page_size,
        }

    # Manual enrichment
    disaster_ids = list(set(d["disaster_id"] for d in base_donations if d.get("disaster_id")))
    request_ids = list(set(d["request_id"] for d in base_donations if d.get("request_id")))

    disaster_map = {}
    if disaster_ids:
        d_resp = await db_admin.table("disasters").select("id, title, type").in_("id", disaster_ids).async_execute()
        for d in d_resp.data or []:
            disaster_map[d["id"]] = d

    request_map = {}
    victim_ids = set()
    if request_ids:
        r_resp = (
            await db_admin.table("resource_requests")
            .select("id, resource_type, description, victim_id")
            .in_("id", request_ids)
            .async_execute()
        )
        for r in r_resp.data or []:
            request_map[r["id"]] = r
            if r.get("victim_id"):
                victim_ids.add(r["victim_id"])

    user_map = {}
    if victim_ids:
        u_resp = await db_admin.table("users").select("id, full_name").in_("id", list(victim_ids)).async_execute()
        for u in u_resp.data or []:
            user_map[u["id"]] = u

    # Flatten disaster and victim info
    final_rows = []
    for r in base_donations:
        d = disaster_map.get(r.get("disaster_id"), {})
        req = request_map.get(r.get("request_id"), {})
        vid = req.get("victim_id")
        v = user_map.get(vid, {})

        # Use disaster title if available, otherwise show request resource type
        if d.get("title"):
            r["disaster_title"] = d["title"]
            r["disaster_type"] = d.get("type", "disaster")
        elif req.get("resource_type"):
            r["disaster_title"] = req["resource_type"]
            r["disaster_type"] = "pledge"
        else:
            r["disaster_title"] = "Donation"
            r["disaster_type"] = "general"

        r["resource_type"] = req.get("resource_type")
        r["description"] = req.get("description")
        r["victim_name"] = v.get("full_name") or None
        r["request_id"] = r.get("request_id")
        final_rows.append(r)
    return {
        "donations": final_rows,
        "total": total_count,
        "page": page,
        "page_size": page_size,
    }


@router.post("/donations")
async def create_donation(body: DonationCreate, donor=Depends(require_verified_donor)):
    """Record a new donation / pledge. Notifies admins and logs to operational_pulse."""
    user_id = donor.get("id")
    donor_name = donor.get("full_name") or donor.get("email") or "Unknown Donor"
    row = {
        "user_id": user_id,
        "disaster_id": body.disaster_id,
        "request_id": body.request_id,
        "amount": body.amount,
        "currency": body.currency,
        "status": body.status,
        "payment_ref": body.payment_ref,
        "notes": body.notes,
        "donation_type": body.donation_type,
        "resource_items": body.resource_items or [],
    }
    resp = await db_admin.table("donations").insert(row).async_execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to record donation")

    donation = resp.data[0]

    # If this is a request-linked pledge, update fulfillment tracking & notify
    if body.request_id:
        # Fetch the request for context
        req_resp = (
            await db_admin.table("resource_requests")
            .select("*")
            .eq("id", body.request_id)
            .maybe_single()
            .async_execute()
        )
        resource_type = "resources"
        if req_resp.data:
            resource_type = req_resp.data.get("resource_type", "resources")
            current_status = req_resp.data.get("status")

            # Track partial fulfillment: update fulfillment_entries on the request
            fulfillment_entries = req_resp.data.get("fulfillment_entries") or []

            # Auto-populate resource_items from request if donor didn't specify any
            donor_resource_items = body.resource_items or []
            if not donor_resource_items and body.donation_type in ("resource", "both"):
                # Calculate remaining quantity needed
                request_items = req_resp.data.get("items") or []
                total_requested = (
                    sum(it.get("quantity", 1) for it in request_items)
                    if request_items
                    else req_resp.data.get("quantity", 1)
                )
                already_fulfilled = sum(
                    ri.get("quantity", 0) for fe in fulfillment_entries for ri in (fe.get("resource_items") or [])
                )
                remaining = max(1, total_requested - already_fulfilled)
                donor_resource_items = [
                    {"resource_type": req_resp.data.get("resource_type", "Resource"), "quantity": remaining}
                ]

            entry = {
                "provider_id": user_id,
                "provider_name": donor_name,
                "provider_role": "donor",
                "donation_id": donation["id"],
                "donation_type": body.donation_type,
                "amount": body.amount if body.donation_type in ("money", "both") else 0,
                "resource_items": donor_resource_items,
                "status": "pledged",
                "created_at": datetime.now(UTC).isoformat(),
            }
            fulfillment_entries.append(entry)

            # Calculate fulfillment progress
            request_items = req_resp.data.get("items") or []
            fulfilled_quantities = {}
            total_money = 0
            for fe in fulfillment_entries:
                for ri in fe.get("resource_items") or []:
                    rt = ri.get("resource_type", "")
                    fulfilled_quantities[rt] = fulfilled_quantities.get(rt, 0) + ri.get("quantity", 0)
                # Track money contributions separately
                if fe.get("donation_type") in ("money", "both") and fe.get("amount", 0) > 0:
                    total_money += fe.get("amount", 0)

            total_requested = (
                sum(it.get("quantity", 1) for it in request_items)
                if request_items
                else req_resp.data.get("quantity", 1)
            )
            total_fulfilled = sum(fulfilled_quantities.values()) if fulfilled_quantities else 0

            # If only money donations exist (no resource items from anyone), treat money
            # as a signal of partial fulfillment so the request progresses
            if total_fulfilled == 0 and total_money > 0:
                fulfillment_pct = min(100, round(total_money / max(total_requested * 100, 1) * 100))
            else:
                fulfillment_pct = min(100, round((total_fulfilled / max(total_requested, 1)) * 100))

            update_fields = {
                "fulfillment_entries": fulfillment_entries,
                "fulfillment_pct": fulfillment_pct,
                "updated_at": datetime.now(UTC).isoformat(),
            }

            # Auto-advance status based on fulfillment
            if fulfillment_pct >= 100:
                # Fully fulfilled by donors/NGOs collectively — ready for admin assignment
                update_fields["status"] = "availability_submitted"
            elif fulfillment_pct > 0 and current_status in ("approved", "under_review", "availability_submitted"):
                update_fields["status"] = "under_review"

            await db_admin.table("resource_requests").update(update_fields).eq("id", body.request_id).async_execute()

        # Compute distance for metadata
        distance_km = None
        try:
            du = await db_admin.table("users").select("metadata").eq("id", user_id).maybe_single().async_execute()
            if du.data and du.data.get("metadata"):
                d_lat = du.data["metadata"].get("latitude")
                d_lon = du.data["metadata"].get("longitude")
                if d_lat and d_lon and req_resp.data:
                    rr = (
                        await db_admin.table("resource_requests")
                        .select("latitude, longitude")
                        .eq("id", body.request_id)
                        .maybe_single()
                        .async_execute()
                    )
                    if rr.data and rr.data.get("latitude") and rr.data.get("longitude"):
                        distance_km = round(
                            haversine_km(d_lat, d_lon, rr.data["latitude"], rr.data["longitude"]),
                            2,
                        )
        except Exception:
            pass

        # Log to operational_pulse
        await _log_pulse(
            actor_id=user_id,
            target_id=body.request_id,
            action_type="donor_pledge_submitted",
            description=f"Donor '{donor_name}' pledged support for request {body.request_id[:8]}...",
            metadata={
                "notes": body.notes,
                "amount": body.amount,
                "distance_km": distance_km,
                "provider_role": "donor",
                "available_quantity": sum(ri.get("quantity", 0) for ri in (body.resource_items or [])) or None,
                "resource_items": body.resource_items or [],
                "donation_type": body.donation_type,
            },
        )

        # Notify all admins
        admin_users = await db_admin.table("users").select("id").eq("role", "admin").async_execute()
        for admin in admin_users.data or []:
            await _send_notification(
                user_id=admin["id"],
                title="Donor Pledge Submitted",
                message=f"Donor '{donor_name}' pledged support for {resource_type} request {body.request_id[:8]}...",
                priority="high",
                data={
                    "request_id": body.request_id,
                    "donor_id": user_id,
                    "type": "donor_pledge",
                },
            )

        # Notify the victim that a donor has pledged to help
        try:
            req_data = (
                await db_admin.table("resource_requests")
                .select("victim_id, resource_type")
                .eq("id", body.request_id)
                .maybe_single()
                .async_execute()
            )
            if req_data.data and req_data.data.get("victim_id"):
                await notify_user(
                    user_id=req_data.data["victim_id"],
                    title="💰 A Donor Has Pledged Support",
                    message=f"A donor has pledged support for your {req_data.data.get('resource_type', 'resource')} request. Help is on the way!",
                    notification_type="success",
                    related_id=body.request_id,
                    related_type="request",
                )
        except Exception:
            pass

    return donation


@router.patch("/donations/{donation_id}")
async def update_donation(donation_id: str, body: DonationUpdate, user_id: str = Depends(get_current_user_id)):
    """Update a donation (e.g. mark completed with amount)."""
    updates = {}
    if body.amount is not None:
        updates["amount"] = body.amount
    if body.status is not None:
        updates["status"] = body.status
    if body.request_id is not None:
        updates["request_id"] = body.request_id
    if body.payment_ref is not None:
        updates["payment_ref"] = body.payment_ref
    if body.notes is not None:
        updates["notes"] = body.notes
    if body.donation_type is not None:
        updates["donation_type"] = body.donation_type
    if body.resource_items is not None:
        updates["resource_items"] = body.resource_items
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.now(UTC).isoformat()
    resp = (
        await db_admin.table("donations").update(updates).eq("id", donation_id).eq("user_id", user_id).async_execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Donation not found")
    return resp.data[0]


@router.get("/donations/{donation_id}/receipt")
async def generate_donation_receipt(donation_id: str, user_id: str = Depends(get_current_user_id)):
    """Generate a digital receipt for a completed donation."""
    # Fetch donation without joins
    resp = (
        await db_admin.table("donations")
        .select("*")
        .eq("id", donation_id)
        .eq("user_id", user_id)
        .single()
        .async_execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Donation not found")

    donation = resp.data
    if donation.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail="Receipts are only available for completed donations",
        )

    # Manual enrichment for disaster and request
    disaster_title = "Unknown Disaster"
    did = donation.get("disaster_id")
    if did:
        d_resp = await db_admin.table("disasters").select("title").eq("id", did).maybe_single().async_execute()
        if d_resp.data:
            disaster_title = d_resp.data.get("title", "Unknown Disaster")

    request_desc = "General Support"
    rid = donation.get("request_id")
    if rid:
        r_resp = (
            await db_admin.table("resource_requests").select("description").eq("id", rid).maybe_single().async_execute()
        )
        if r_resp.data:
            request_desc = r_resp.data.get("description", "General Support")

    # Generate a simple formatted receipt
    receipt = {
        "receipt_id": f"REC-{donation['id'][:8].upper()}",
        "date": donation["updated_at"],
        "donor_id": user_id,
        "amount": donation["amount"],
        "currency": donation["currency"],
        "cause": disaster_title,
        "allocated_to": (request_desc if donation.get("request_id") else "General Disaster Relief Fund"),
        "payment_reference": donation.get("payment_ref", "N/A"),
        "status": "COMPLETED",
        "message": "Thank you for your generous contribution to disaster relief efforts.",
    }
    return receipt


@router.get("/donations/{donation_id}/tax-certificate")
async def generate_tax_certificate(donation_id: str, user_id: str = Depends(get_current_user_id)):
    """Generate a PDF tax deduction certificate for a completed donation."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    # Fetch donation
    resp = (
        await db_admin.table("donations")
        .select("*")
        .eq("id", donation_id)
        .eq("user_id", user_id)
        .single()
        .async_execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Donation not found")

    donation = resp.data
    if donation.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail="Tax certificates are only available for completed donations",
        )

    # Fetch donor profile
    donor_resp = (
        await db_admin.table("users").select("full_name, email").eq("id", user_id).maybe_single().async_execute()
    )
    donor_name = "Donor"
    donor_email = ""
    if donor_resp.data:
        donor_name = donor_resp.data.get("full_name") or "Donor"
        donor_email = donor_resp.data.get("email") or ""

    # Fetch disaster info
    disaster_title = "General Disaster Relief"
    did = donation.get("disaster_id")
    if did:
        d_resp = await db_admin.table("disasters").select("title, type").eq("id", did).maybe_single().async_execute()
        if d_resp.data:
            disaster_title = d_resp.data.get("title", disaster_title)

    # Fetch linked request
    request_desc = "General Support"
    rid = donation.get("request_id")
    if rid:
        r_resp = (
            await db_admin.table("resource_requests")
            .select("description, resource_type")
            .eq("id", rid)
            .maybe_single()
            .async_execute()
        )
        if r_resp.data:
            request_desc = r_resp.data.get("description") or r_resp.data.get("resource_type") or "General Support"

    # Build PDF
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CertTitle", parent=styles["Title"], fontSize=22, textColor=colors.HexColor("#065f46"), spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        "CertSub", parent=styles["Normal"], fontSize=11, alignment=TA_CENTER, textColor=colors.grey, spaceAfter=20
    )
    heading_style = ParagraphStyle(
        "CertHead",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=colors.HexColor("#065f46"),
        spaceBefore=16,
        spaceAfter=8,
    )
    ParagraphStyle("CertNormal", parent=styles["Normal"], fontSize=10, leading=14)
    small_style = ParagraphStyle(
        "CertSmall", parent=styles["Normal"], fontSize=8, textColor=colors.grey, alignment=TA_CENTER, spaceBefore=20
    )

    receipt_id = f"REC-{donation['id'][:8].upper()}"
    cert_date = datetime.fromisoformat(donation["updated_at"].replace("Z", "+00:00")).strftime("%B %d, %Y")
    donation_date = datetime.fromisoformat(donation["created_at"].replace("Z", "+00:00")).strftime("%B %d, %Y")

    elements = []

    # Header
    elements.append(Paragraph("HopeInChaos", title_style))
    elements.append(Paragraph("Disaster Resource Management System", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#10b981"), spaceAfter=12))

    # Certificate title
    cert_title = ParagraphStyle("BigTitle", parent=styles["Title"], fontSize=18, alignment=TA_CENTER, spaceAfter=6)
    elements.append(Paragraph("Tax Deduction Certificate", cert_title))
    elements.append(
        Paragraph(
            f"Certificate No: {receipt_id}",
            ParagraphStyle(
                "RefNo", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER, textColor=colors.grey, spaceAfter=16
            ),
        )
    )

    # Donor details
    elements.append(Paragraph("Donor Information", heading_style))
    donor_data = [
        ["Donor Name:", donor_name],
        ["Email:", donor_email],
        ["Donor ID:", user_id[:12] + "..."],
        ["Certificate Date:", cert_date],
    ]
    donor_table = Table(donor_data, colWidths=[120, 340])
    donor_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#111827")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elements.append(donor_table)

    # Donation details
    elements.append(Paragraph("Donation Details", heading_style))
    donation_type = donation.get("donation_type", "money")
    amount = donation.get("amount", 0)
    currency = donation.get("currency", "USD")
    resource_items = donation.get("resource_items") or []

    donation_data = [
        ["Donation Date:", donation_date],
        ["Donation Type:", donation_type.capitalize()],
        ["Cause:", disaster_title],
        ["Allocated To:", request_desc[:60]],
        ["Payment Reference:", donation.get("payment_ref") or "N/A"],
    ]

    if donation_type in ("money", "both") and amount > 0:
        donation_data.insert(2, ["Amount:", f"${amount:,.2f} {currency}"])

    donation_table = Table(donation_data, colWidths=[120, 340])
    donation_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#111827")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elements.append(donation_table)

    # Resource items table (if applicable)
    if resource_items:
        elements.append(Paragraph("Donated Resources", heading_style))
        res_header = [["Resource Type", "Quantity", "Unit"]]
        res_rows = [
            [ri.get("resource_type", "—"), str(ri.get("quantity", 0)), ri.get("unit", "units")] for ri in resource_items
        ]
        res_table = Table(res_header + res_rows, colWidths=[200, 120, 140])
        res_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ]
            )
        )
        elements.append(res_table)

    # Disclaimer
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey, spaceAfter=12))
    elements.append(Paragraph("Tax Deduction Disclaimer", heading_style))
    disclaimer_style = ParagraphStyle(
        "Disclaimer", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#6b7280"), leading=13
    )
    elements.append(
        Paragraph(
            "This certificate is issued as an acknowledgment of your donation to disaster relief efforts "
            "through HopeInChaos. Please consult with a qualified tax advisor to determine whether this "
            "donation qualifies for a tax deduction under applicable laws. HopeInChaos does not provide "
            "tax, legal, or accounting advice. The information contained herein is for informational purposes only.",
            disclaimer_style,
        )
    )

    # Footer
    elements.append(Spacer(1, 30))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#10b981"), spaceAfter=8))
    elements.append(Paragraph("HopeInChaos — Disaster Resource Management System", small_style))
    elements.append(Paragraph(f"Generated on {datetime.now(UTC).strftime('%B %d, %Y at %H:%M UTC')}", small_style))

    doc.build(elements)
    buf.seek(0)

    filename = f"tax-certificate-{receipt_id}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/donations/{donation_id}")
async def delete_donation(donation_id: str, user_id: str = Depends(get_current_user_id)):
    """Remove a donation record."""
    await db_admin.table("donations").delete().eq("id", donation_id).eq("user_id", user_id).async_execute()
    return {"deleted": True}


# ── Pledge Endpoints ──────────────────────────────────────────────────────────


@router.get("/pledges")
async def list_pledges(user_id: str = Depends(get_current_user_id)):
    """List all pledged causes for the authenticated donor."""
    resp = (
        await db_admin.table("donor_pledges")
        .select("*")
        .eq("donor_id", user_id)
        .order("created_at", desc=True)
        .async_execute()
    )
    base_pledges = resp.data or []

    # Manual enrichment for disasters
    disaster_ids = list(set(p["disaster_id"] for p in base_pledges if p.get("disaster_id")))
    disaster_map = {}
    if disaster_ids:
        d_resp = (
            await db_admin.table("disasters")
            .select("id, title, type, severity, status")
            .in_("id", disaster_ids)
            .async_execute()
        )
        for d in d_resp.data or []:
            disaster_map[d["id"]] = d

    pledges = []
    for p in base_pledges:
        p["disasters"] = disaster_map.get(p.get("disaster_id"))
        pledges.append(p)
    return pledges


@router.post("/pledges")
async def create_pledge(body: PledgeCreate, donor=Depends(require_verified_donor)):
    """Pledge support for a disaster cause."""
    user_id = donor.get("id")
    row = {"donor_id": user_id, "disaster_id": body.disaster_id}
    resp = await db_admin.table("donor_pledges").insert(row).async_execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create pledge")
    return resp.data[0]


@router.delete("/pledges/{disaster_id}")
async def remove_pledge(disaster_id: str, user_id: str = Depends(get_current_user_id)):
    """Remove a pledge."""
    await (
        db_admin.table("donor_pledges").delete().eq("disaster_id", disaster_id).eq("donor_id", user_id).async_execute()
    )
    return {"deleted": True}


# ── Donor Stats ───────────────────────────────────────────────────────────────


@router.get("/stats")
async def donor_stats(user_id: str = Depends(get_current_user_id)):
    """Aggregated stats for the donor dashboard."""
    donations_resp = (
        await db_admin.table("donations")
        .select("amount, status, donation_type, resource_items")
        .eq("user_id", user_id)
        .async_execute()
    )
    donations = donations_resp.data or []
    completed = [d for d in donations if d["status"] == "completed"]
    total_donated = sum(float(d.get("amount", 0)) for d in completed)
    resource_donations = [d for d in donations if d.get("donation_type") in ("resource", "both")]
    total_resource_items = sum(
        sum(ri.get("quantity", 0) for ri in (d.get("resource_items") or [])) for d in resource_donations
    )

    pledges_resp = await db_admin.table("donor_pledges").select("id").eq("donor_id", user_id).async_execute()
    pledges = pledges_resp.data or []

    return {
        "total_donations": len(donations),
        "completed_donations": len(completed),
        "pending_donations": len(donations) - len(completed),
        "total_donated": total_donated,
        "resource_donations": len(resource_donations),
        "total_resource_items": total_resource_items,
        "causes_supported": len(pledges),
        "impact_score": min(
            100, round(total_donated / 100 + len(completed) * 5 + len(pledges) * 2 + total_resource_items)
        ),
    }
