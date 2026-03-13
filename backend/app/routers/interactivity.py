from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.database import db_admin
from app.dependencies import get_current_user, require_role
from app.schemas import (
    DonorPledge,
    DonorPledgeCreate,
    MissionTask,
    MissionTaskCreate,
    NgoMobilization,
    NgoMobilizationCreate,
    OperationalPulse,
    RequestVerification,
    RequestVerificationCreate,
    ResourceSourcing,
    ResourceSourcingCreate,
    VolunteerProfile,
    VolunteerProfileUpdate,
)
from app.services.notification_service import (
    notify_all_admins,
    notify_user,
)

router = APIRouter(prefix="/api/interactivity", tags=["Interactivity"])


# --- Helper: Log Operational Pulse ---
async def log_pulse(actor_id: str, action_type: str, target_id: str, description: str, metadata: dict = {}):
    try:
        pulse_data = {
            "id": str(uuid4()),
            "actor_id": actor_id,
            "target_id": target_id,
            "action_type": action_type,
            "description": description,
            "metadata": metadata,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db_admin.table("operational_pulse").insert(pulse_data).async_execute()
    except Exception as e:
        print(f"Failed to log pulse: {e}")


# --- Volunteer ↔ Victim: Verification ---
@router.post("/verify-request", response_model=RequestVerification)
async def verify_victim_request(
    data: RequestVerificationCreate,
    user=Depends(require_role("volunteer")),
    bg_tasks: BackgroundTasks = BackgroundTasks(),
):
    # 1. Update the request status
    req_update = {
        "is_verified": True,
        "verification_status": data.verification_status,
        "verified_at": datetime.now(UTC).isoformat(),
        "verified_by": user["id"],
    }
    await db_admin.table("resource_requests").update(req_update).eq("id", data.request_id).async_execute()

    # 2. Insert verification log
    v_log = {
        "id": str(uuid4()),
        "request_id": data.request_id,
        "volunteer_id": user["id"],
        "field_notes": data.field_notes,
        "photo_url": data.photo_url,
        "verification_status": data.verification_status,
        "latitude_at_verification": data.latitude_at_verification,
        "longitude_at_verification": data.longitude_at_verification,
    }
    result = await db_admin.table("request_verifications").insert(v_log).async_execute()

    # 3. Log pulse
    bg_tasks.add_task(
        log_pulse,
        user["id"],
        "VERIFIED_REQUEST",
        data.request_id,
        f"Volunteer verified request {data.request_id} as {data.verification_status}",
    )

    # 4. Notify admin & victim about verification
    async def _notify_verification():
        try:
            await notify_all_admins(
                title="🔍 Request Verified by Volunteer",
                message=f"Request {data.request_id[:8]}... verified as '{data.verification_status}'.",
                notification_type="info",
                related_id=data.request_id,
                related_type="request",
            )
            # Notify victim
            req = (
                await db_admin.table("resource_requests")
                .select("victim_id")
                .eq("id", data.request_id)
                .maybe_single()
                .async_execute()
            )
            if req.data and req.data.get("victim_id"):
                await notify_user(
                    user_id=req.data["victim_id"],
                    title="✅ Your Request Has Been Verified",
                    message=f"A volunteer has verified your request on the ground. Status: {data.verification_status}.",
                    notification_type="success",
                    related_id=data.request_id,
                    related_type="request",
                )
        except Exception:
            pass

    bg_tasks.add_task(_notify_verification)

    return result.data[0]


# --- NGO ↔ Donor: Sourcing ---
@router.post("/sourcing-request", response_model=ResourceSourcing)
async def create_sourcing_request(
    data: ResourceSourcingCreate, user=Depends(require_role("ngo")), bg_tasks: BackgroundTasks = BackgroundTasks()
):
    s_data = {"id": str(uuid4()), "ngo_id": user["id"], **data.dict()}
    result = await db_admin.table("resource_sourcing_requests").insert(s_data).async_execute()

    bg_tasks.add_task(
        log_pulse,
        user["id"],
        "CREATED_SOURCING",
        result.data[0]["id"],
        f"NGO {user.get('organization', user['id'])} requested {data.quantity_needed} {data.resource_type}",
    )

    return result.data[0]


@router.post("/pledge", response_model=DonorPledge)
async def pledge_to_sourcing(
    data: DonorPledgeCreate, user=Depends(require_role("donor")), bg_tasks: BackgroundTasks = BackgroundTasks()
):
    # 1. Check ifourcing exists
    s_req = (
        await db_admin.table("resource_sourcing_requests")
        .select("*")
        .eq("id", data.sourcing_request_id)
        .async_execute()
    )
    if not s_req.data:
        raise HTTPException(status_code=404, detail="Sourcing request not found")

    # 2. Insert pledge
    p_data = {"id": str(uuid4()), "donor_id": user["id"], **data.dict()}
    result = await db_admin.table("donor_pledges").insert(p_data).async_execute()

    # 3. Update sourcing status to partially_funded if it was open
    if s_req.data[0]["status"] == "open":
        await (
            db_admin.table("resource_sourcing_requests")
            .update({"status": "partially_funded"})
            .eq("id", data.sourcing_request_id)
            .async_execute()
        )

    bg_tasks.add_task(
        log_pulse,
        user["id"],
        "PLEDGED_RESOURCES",
        data.sourcing_request_id,
        f"Donor pledged {data.quantity_pledged} units to sourcing request {data.sourcing_request_id}",
    )

    return result.data[0]


# --- NGO ↔ Volunteer: Mobilization ---
@router.post("/mobilize", response_model=NgoMobilization)
async def create_mobilization(
    data: NgoMobilizationCreate, user=Depends(require_role("ngo")), bg_tasks: BackgroundTasks = BackgroundTasks()
):
    m_data = {"id": str(uuid4()), "ngo_id": user["id"], **data.dict()}
    result = await db_admin.table("ngo_mobilization").insert(m_data).async_execute()

    bg_tasks.add_task(
        log_pulse,
        user["id"],
        "CREATED_MOBILIZATION",
        result.data[0]["id"],
        f"NGO created mobilization mission: {data.title}",
    )

    return result.data[0]


@router.post("/join-mission/{mobilization_id}")
async def join_mission(
    mobilization_id: str, user=Depends(require_role("volunteer")), bg_tasks: BackgroundTasks = BackgroundTasks()
):
    assignment = {
        "id": str(uuid4()),
        "mobilization_id": mobilization_id,
        "volunteer_id": user["id"],
        "status": "assigned",
    }
    result = await db_admin.table("volunteer_assignments").insert(assignment).async_execute()

    bg_tasks.add_task(
        log_pulse, user["id"], "JOINED_MISSION", mobilization_id, f"Volunteer joined mission {mobilization_id}"
    )

    # Notify the NGO lead that a volunteer joined their mission
    async def _notify_ngo_lead():
        try:
            mob = (
                await db_admin.table("ngo_mobilization")
                .select("ngo_id, title")
                .eq("id", mobilization_id)
                .maybe_single()
                .async_execute()
            )
            if mob.data and mob.data.get("ngo_id"):
                vol_name = user.get("full_name") or user.get("email") or "A volunteer"
                await notify_user(
                    user_id=mob.data["ngo_id"],
                    title="👤 Volunteer Joined Your Mission",
                    message=f"{vol_name} has joined your mission: {mob.data.get('title', mobilization_id[:8])}.",
                    notification_type="success",
                    related_id=mobilization_id,
                    related_type="mobilization",
                )
        except Exception:
            pass

    bg_tasks.add_task(_notify_ngo_lead)

    return result.data[0]


# --- Admin: Pulse ---
@router.get("/operational-pulse", response_model=list[OperationalPulse])
async def get_operational_pulse(limit: int = 50, user=Depends(require_role("admin"))):
    result = (
        await db_admin.table("operational_pulse")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .async_execute()
    )
    return result.data


# --- Public: Get Active Missions & Needs ---
@router.get("/active-needs", response_model=list[ResourceSourcing])
async def get_active_needs():
    result = (
        await db_admin.table("resource_sourcing_requests")
        .select("*")
        .neq("status", "closed")
        .order("created_at", desc=True)
        .async_execute()
    )
    return result.data


@router.get("/active-missions", response_model=list[NgoMobilization])
async def get_active_missions():
    result = (
        await db_admin.table("ngo_mobilization")
        .select("*")
        .eq("status", "active")
        .order("created_at", desc=True)
        .async_execute()
    )
    return result.data


# --- Phase 6.5: Advanced Coordination ---


@router.post("/adopt-request/{request_id}")
async def adopt_victim_request(
    request_id: str, user=Depends(require_role("donor")), bg_tasks: BackgroundTasks = BackgroundTasks()
):
    """Direct Donor-to-Victim linking."""
    # 1. Verify existence and trust
    req = await db_admin.table("resource_requests").select("*").eq("id", request_id).single().async_execute()
    if not req.data:
        raise HTTPException(status_code=404, detail="Request not found")
    if not req.data.get("is_verified"):
        raise HTTPException(status_code=400, detail="Only verified requests can be adopted directly")

    # 2. Update status
    update_data = {
        "adopted_by": user["id"],
        "adoption_status": "pledged",
        "status": "assigned",
        "assigned_to": user["id"],
        "assigned_role": "donor",
    }
    result = await db_admin.table("resource_requests").update(update_data).eq("id", request_id).async_execute()

    # 3. Log pulse
    bg_tasks.add_task(
        log_pulse,
        user["id"],
        "ADOPTED_REQUEST",
        request_id,
        f"Donor {user.get('full_name', 'Anonymous')} adopted verified request {request_id} for direct fulfillment.",
    )

    # 4. Notify victim and admin
    async def _notify_adoption():
        try:
            victim_id = req.data.get("victim_id")
            if victim_id:
                await notify_user(
                    user_id=victim_id,
                    title="🎁 A Donor Has Adopted Your Request",
                    message=f"A donor has directly adopted your request for {req.data.get('resource_type', 'resources')}. Help is coming!",
                    notification_type="success",
                    related_id=request_id,
                    related_type="request",
                )
            await notify_all_admins(
                title="💎 Donor Adopted Request",
                message=f"Donor {user.get('full_name', 'Anonymous')} directly adopted request {request_id[:8]}...",
                notification_type="info",
                related_id=request_id,
                related_type="request",
            )
        except Exception:
            pass

    bg_tasks.add_task(_notify_adoption)

    return result.data[0]


class FeedbackBody(BaseModel):
    feedback: str = ""


@router.post("/complete-assignment/{assignment_id}")
async def complete_volunteer_assignment(
    assignment_id: str,
    body: FeedbackBody,
    user=Depends(require_role("volunteer")),
    bg_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Closes the loop between NGO mission and Volunteer action."""
    # 1. Update assignment
    update_data = {
        "status": "completed",
        "feedback_notes": body.feedback,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    result = (
        await db_admin.table("volunteer_assignments")
        .update(update_data)
        .eq("id", assignment_id)
        .eq("volunteer_id", user["id"])
        .async_execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Assignment not found or unauthorized")

    # 2. Reward volunteer (Trust System)
    await db_admin.rpc("increment_user_impact", {"user_id": user["id"], "points": 5}).async_execute()

    # 3. Log pulse
    bg_tasks.add_task(
        log_pulse,
        user["id"],
        "COMPLETED_ASSIGNMENT",
        assignment_id,
        "Volunteer completed assigned mission task and earned impact points.",
    )

    return result.data[0]


@router.get("/urgent-clusters")
async def get_urgent_clusters(user=Depends(require_role("ngo", "admin"))):
    """Spatial intelligence for NGOs to see where help is needed most."""
    result = await db_admin.table("urgent_verification_clusters").select("*").async_execute()
    return result.data


@router.get("/my-impact")
async def get_my_impact(user=Depends(get_current_user)):
    """Personal motivation endpoint showing trust score and points."""
    result = (
        await db_admin.table("users")
        .select("trust_score, total_impact_points, role")
        .eq("id", user["id"])
        .single()
        .async_execute()
    )
    return result.data


# --- Phase 6.6: Deep Interaction ---


@router.get("/volunteer/profile", response_model=VolunteerProfile)
async def get_volunteer_profile(user=Depends(require_role("volunteer"))):
    result = (
        await db_admin.table("volunteer_profiles").select("*").eq("user_id", user["id"]).maybe_single().async_execute()
    )
    if not result.data:
        # Auto-create if not exists
        profile = {"user_id": user["id"], "skills": [], "assets": [], "availability_status": "available"}
        result = await db_admin.table("volunteer_profiles").insert(profile).async_execute()
    return result.data[0] if isinstance(result.data, list) else result.data


@router.patch("/volunteer/profile", response_model=VolunteerProfile)
async def update_volunteer_profile(data: VolunteerProfileUpdate, user=Depends(require_role("volunteer"))):
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(UTC).isoformat()
    result = await db_admin.table("volunteer_profiles").update(update_data).eq("user_id", user["id"]).async_execute()
    return result.data[0]


@router.post("/mission-tasks", response_model=MissionTask)
async def create_mission_task(data: MissionTaskCreate, user=Depends(require_role("ngo"))):
    task_data = {"id": str(uuid4()), "mobilization_id": data.mobilization_id, "task_description": data.task_description}
    result = await db_admin.table("mission_tasks").insert(task_data).async_execute()
    return result.data[0]


@router.patch("/mission-tasks/{task_id}/complete")
async def complete_mission_task(task_id: str, user=Depends(require_role("volunteer", "ngo"))):
    update_data = {"is_completed": True, "completed_by": user["id"], "completed_at": datetime.now(UTC).isoformat()}
    result = await db_admin.table("mission_tasks").update(update_data).eq("id", task_id).async_execute()
    return result.data[0]


@router.post("/confirm-delivery/{request_id}")
async def confirm_aid_delivery(
    request_id: str,
    code: str,
    user=Depends(require_role("volunteer", "donor", "ngo")),
    bg_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Secure handshake using the 6-digit code from the victim."""
    # 1. Verify code
    req = await db_admin.table("resource_requests").select("*").eq("id", request_id).single().async_execute()
    if not req.data:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.data.get("delivery_confirmation_code") != code.upper():
        # Small grace for case sensitivity handled by .upper()
        raise HTTPException(status_code=403, detail="Invalid confirmation code")

    # 2. Update status to completed
    update_data = {"status": "completed", "delivery_confirmed_at": datetime.now(UTC).isoformat()}
    result = await db_admin.table("resource_requests").update(update_data).eq("id", request_id).async_execute()

    # 3. Reward the deliverer
    await db_admin.rpc("increment_user_impact", {"user_id": user["id"], "points": 10}).async_execute()

    bg_tasks.add_task(
        log_pulse,
        user["id"],
        "DELIVERED_AID",
        request_id,
        f"Deliverer successfully completed handshake for request {request_id}.",
    )

    return {"message": "Delivery confirmed and points awarded", "request": result.data[0]}
