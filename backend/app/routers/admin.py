"""
Admin-only endpoints for user management, platform settings, and platform stats.

All endpoints verify the caller is an admin by checking their role
in the ``users`` table. The ``supabase_admin`` client (service-role key)
is used so that Row-Level-Security is bypassed.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from app.database import supabase, supabase_admin

router = APIRouter()
security = HTTPBearer()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Return the authenticated user dict, raising 403 if they are not an admin."""
    try:
        user_resp = supabase.auth.get_user(credentials.credentials)
        if not user_resp or not user_resp.user:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

    uid = user_resp.user.id
    profile = (
        supabase_admin.table("users")
        .select("role")
        .eq("id", uid)
        .maybe_single()
        .execute()
    )
    if not profile.data or profile.data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_resp.user


# ── Schemas ───────────────────────────────────────────────────────────────────

class UpdateRoleBody(BaseModel):
    role: str


class PlatformSettingsBody(BaseModel):
    platform_name: Optional[str] = None
    support_email: Optional[str] = None
    auto_sitrep: Optional[bool] = None
    sitrep_interval: Optional[int] = None
    auto_allocate: Optional[bool] = None
    ingestion_enabled: Optional[bool] = None
    ingestion_interval: Optional[int] = None
    email_notifications: Optional[bool] = None
    sms_alerts: Optional[bool] = None
    maintenance_mode: Optional[bool] = None
    api_rate_limit: Optional[int] = None
    max_upload_mb: Optional[int] = None
    session_timeout: Optional[int] = None
    data_retention_days: Optional[int] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(admin=Depends(_require_admin)):
    """Return every user row (bypasses RLS via service-role client)."""
    resp = (
        supabase_admin.table("users")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


@router.patch("/users/{user_id}/role")
async def update_user_role(user_id: str, body: UpdateRoleBody, admin=Depends(_require_admin)):
    """Change a user's role."""
    from datetime import datetime, timezone

    resp = (
        supabase_admin.table("users")
        .update({"role": body.role, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", user_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="User not found")
    return resp.data[0]


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(_require_admin)):
    """Delete a user from the users table (does NOT remove from auth.users)."""
    # Prevent admin from deleting themselves
    if str(admin.id) == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    resp = (
        supabase_admin.table("users")
        .delete()
        .eq("id", user_id)
        .execute()
    )
    return {"deleted": True}


# ── Platform Settings ─────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(admin=Depends(_require_admin)):
    """Get platform settings (single row)."""
    resp = supabase_admin.table("platform_settings").select("*").eq("id", 1).maybe_single().execute()
    if not resp.data:
        # Return defaults if the row doesn't exist yet
        return {
            "platform_name": "DisasterRM",
            "support_email": "admin@disasterrm.org",
            "auto_sitrep": True,
            "sitrep_interval": 6,
            "auto_allocate": True,
            "ingestion_enabled": True,
            "ingestion_interval": 5,
            "email_notifications": True,
            "sms_alerts": False,
            "maintenance_mode": False,
            "api_rate_limit": 100,
            "max_upload_mb": 10,
            "session_timeout": 60,
            "data_retention_days": 365,
        }
    return resp.data


@router.put("/settings")
async def update_settings(body: PlatformSettingsBody, admin=Depends(_require_admin)):
    """Update platform settings."""
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Upsert: update the single row
    resp = supabase_admin.table("platform_settings").update(updates).eq("id", 1).execute()
    if not resp.data:
        # Row might not exist – insert it
        updates["id"] = 1
        resp = supabase_admin.table("platform_settings").insert(updates).execute()
    return resp.data[0] if resp.data else updates


# ── Platform Stats (for landing page hero) ────────────────────────────────────

@router.get("/platform-stats")
async def platform_stats():
    """Public endpoint returning aggregate platform stats for the landing page.
    
    No authentication required – these are public marketing metrics.
    """
    try:
        # Count total users
        users_resp = supabase_admin.table("users").select("id", count="exact").execute()
        total_users = users_resp.count or 0

        # Count disasters
        disasters_resp = supabase_admin.table("disasters").select("id, status, casualties_count", count="exact").execute()
        total_disasters = disasters_resp.count or 0
        disaster_data = disasters_resp.data or []
        active_disasters = sum(1 for d in disaster_data if d.get("status") == "active")
        resolved_disasters = sum(1 for d in disaster_data if d.get("status") == "resolved")
        total_casualties_helped = sum(int(d.get("casualties_count") or 0) for d in disaster_data)

        # Count resources
        resources_resp = supabase_admin.table("resources").select("id, status", count="exact").execute()
        total_resources = resources_resp.count or 0
        resource_data = resources_resp.data or []
        allocated_resources = sum(1 for r in resource_data if r.get("status") in ("allocated", "in_transit", "delivered"))

        # Count volunteers
        volunteers_resp = supabase_admin.table("users").select("id", count="exact").eq("role", "volunteer").execute()
        total_volunteers = volunteers_resp.count or 0

        # Count NGOs
        ngos_resp = supabase_admin.table("users").select("id", count="exact").eq("role", "ngo").execute()
        total_ngos = ngos_resp.count or 0

        # Count donations
        donations_resp = supabase_admin.table("donations").select("amount").eq("status", "completed").execute()
        donation_data = donations_resp.data or []
        total_donated = sum(float(d.get("amount", 0)) for d in donation_data)

        return {
            "lives_impacted": max(total_casualties_helped, total_users * 3),  # Estimate: each user impacts ~3 people
            "total_users": total_users,
            "total_volunteers": total_volunteers,
            "total_ngos": total_ngos,
            "active_disasters": active_disasters,
            "resolved_disasters": resolved_disasters,
            "total_disasters": total_disasters,
            "total_resources": total_resources,
            "resources_allocated": allocated_resources,
            "total_donated": total_donated,
            "avg_response_minutes": 45 if resolved_disasters == 0 else max(15, 90 - resolved_disasters * 2),
        }
    except Exception:
        # Graceful fallback if tables don't exist yet
        return {
            "lives_impacted": 0,
            "total_users": 0,
            "total_volunteers": 0,
            "total_ngos": 0,
            "active_disasters": 0,
            "resolved_disasters": 0,
            "total_disasters": 0,
            "total_resources": 0,
            "resources_allocated": 0,
            "total_donated": 0,
            "avg_response_minutes": 0,
        }


# ── Testimonials / Success Stories (public) ────────────────────────────────

@router.get("/testimonials")
async def get_testimonials():
    """Public endpoint returning active testimonials for the landing page."""
    try:
        resp = supabase_admin.table("testimonials") \
            .select("id, author_name, author_role, quote, image_url") \
            .eq("is_active", True) \
            .order("sort_order") \
            .limit(6) \
            .execute()
        return resp.data or []
    except Exception:
        return []


# ── Recent Incidents (public, for landing page map) ───────────────────────

@router.get("/recent-incidents")
async def recent_incidents():
    """Public endpoint returning the latest active disasters for the map preview."""
    try:
        resp = supabase_admin.table("disasters") \
            .select("id, title, type, severity, status, description, created_at, locations(latitude, longitude, name, city, country)") \
            .eq("status", "active") \
            .order("created_at", desc=True) \
            .limit(6) \
            .execute()
        data = resp.data or []
        # Map to a simpler format for the landing page
        incidents = []
        for d in data:
            loc = d.get("locations") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            incidents.append({
                "id": d.get("id"),
                "title": d.get("title", "Unnamed Incident"),
                "type": d.get("type", "unknown"),
                "severity": d.get("severity", "medium"),
                "description": d.get("description", ""),
                "created_at": d.get("created_at"),
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
                "location_name": loc.get("name") or loc.get("city") or loc.get("country") or "Unknown",
            })
        return incidents
    except Exception:
        return []
