from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from app.database import supabase_admin
from app.dependencies import get_current_user, require_role
from app.schemas import (
    RequestVerificationCreate, RequestVerification,
    ResourceSourcingCreate, ResourceSourcing,
    DonorPledgeCreate, DonorPledge,
    NgoMobilizationCreate, NgoMobilization,
    VolunteerAssignment, OperationalPulse,
    AssignmentStatus, SourcingStatus, PledgeStatus, MobilizationStatus,
    VolunteerProfileUpdate, VolunteerProfile, MissionTaskCreate, MissionTask
)
from uuid import uuid4
from datetime import datetime, timezone

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
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        supabase_admin.table("operational_pulse").insert(pulse_data).execute()
    except Exception as e:
        print(f"Failed to log pulse: {e}")

# --- Volunteer ↔ Victim: Verification ---
@router.post("/verify-request", response_model=RequestVerification)
async def verify_victim_request(
    data: RequestVerificationCreate,
    user=Depends(require_role("volunteer")),
    bg_tasks: BackgroundTasks = BackgroundTasks()
):
    # 1. Update the request status
    req_update = {
        "is_verified": True,
        "verification_status": data.verification_status,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "verified_by": user["id"]
    }
    supabase_admin.table("resource_requests").update(req_update).eq("id", data.request_id).execute()

    # 2. Insert verification log
    v_log = {
        "id": str(uuid4()),
        "request_id": data.request_id,
        "volunteer_id": user["id"],
        "field_notes": data.field_notes,
        "photo_url": data.photo_url,
        "verification_status": data.verification_status,
        "latitude_at_verification": data.latitude_at_verification,
        "longitude_at_verification": data.longitude_at_verification
    }
    result = supabase_admin.table("request_verifications").insert(v_log).execute()
    
    # 3. Log pulse
    bg_tasks.add_task(log_pulse, user["id"], "VERIFIED_REQUEST", data.request_id, f"Volunteer verified request {data.request_id} as {data.verification_status}")
    
    return result.data[0]

# --- NGO ↔ Donor: Sourcing ---
@router.post("/sourcing-request", response_model=ResourceSourcing)
async def create_sourcing_request(
    data: ResourceSourcingCreate,
    user=Depends(require_role("ngo")),
    bg_tasks: BackgroundTasks = BackgroundTasks()
):
    s_data = {
        "id": str(uuid4()),
        "ngo_id": user["id"],
        **data.dict()
    }
    result = supabase_admin.table("resource_sourcing_requests").insert(s_data).execute()
    
    bg_tasks.add_task(log_pulse, user["id"], "CREATED_SOURCING", result.data[0]["id"], f"NGO {user.get('organization', user['id'])} requested {data.quantity_needed} {data.resource_type}")
    
    return result.data[0]

@router.post("/pledge", response_model=DonorPledge)
async def pledge_to_sourcing(
    data: DonorPledgeCreate,
    user=Depends(require_role("donor")),
    bg_tasks: BackgroundTasks = BackgroundTasks()
):
    # 1. Check ifourcing exists
    s_req = supabase_admin.table("resource_sourcing_requests").select("*").eq("id", data.sourcing_request_id).execute()
    if not s_req.data:
        raise HTTPException(status_code=404, detail="Sourcing request not found")

    # 2. Insert pledge
    p_data = {
        "id": str(uuid4()),
        "donor_id": user["id"],
        **data.dict()
    }
    result = supabase_admin.table("donor_pledges").insert(p_data).execute()
    
    # 3. Update sourcing status to partially_funded if it was open
    if s_req.data[0]["status"] == "open":
        supabase_admin.table("resource_sourcing_requests").update({"status": "partially_funded"}).eq("id", data.sourcing_request_id).execute()

    bg_tasks.add_task(log_pulse, user["id"], "PLEDGED_RESOURCES", data.sourcing_request_id, f"Donor pledged {data.quantity_pledged} units to sourcing request {data.sourcing_request_id}")
    
    return result.data[0]

# --- NGO ↔ Volunteer: Mobilization ---
@router.post("/mobilize", response_model=NgoMobilization)
async def create_mobilization(
    data: NgoMobilizationCreate,
    user=Depends(require_role("ngo")),
    bg_tasks: BackgroundTasks = BackgroundTasks()
):
    m_data = {
        "id": str(uuid4()),
        "ngo_id": user["id"],
        **data.dict()
    }
    result = supabase_admin.table("ngo_mobilization").insert(m_data).execute()
    
    bg_tasks.add_task(log_pulse, user["id"], "CREATED_MOBILIZATION", result.data[0]["id"], f"NGO created mobilization mission: {data.title}")
    
    return result.data[0]

@router.post("/join-mission/{mobilization_id}")
async def join_mission(
    mobilization_id: str,
    user=Depends(require_role("volunteer")),
    bg_tasks: BackgroundTasks = BackgroundTasks()
):
    assignment = {
        "id": str(uuid4()),
        "mobilization_id": mobilization_id,
        "volunteer_id": user["id"],
        "status": "assigned"
    }
    result = supabase_admin.table("volunteer_assignments").insert(assignment).execute()
    
    bg_tasks.add_task(log_pulse, user["id"], "JOINED_MISSION", mobilization_id, f"Volunteer joined mission {mobilization_id}")
    
    return result.data[0]

# --- Admin: Pulse ---
@router.get("/operational-pulse", response_model=List[OperationalPulse])
async def get_operational_pulse(
    limit: int = 50,
    user=Depends(require_role("admin"))
):
    result = supabase_admin.table("operational_pulse")\
        .select("*")\
        .order("created_at", desc=True)\
        .limit(limit)\
        .execute()
    return result.data

# --- Public: Get Active Missions & Needs ---
@router.get("/active-needs", response_model=List[ResourceSourcing])
async def get_active_needs():
    result = supabase_admin.table("resource_sourcing_requests")\
        .select("*")\
        .neq("status", "closed")\
        .order("created_at", desc=True)\
        .execute()
    return result.data

@router.get("/active-missions", response_model=List[NgoMobilization])
async def get_active_missions():
    result = supabase_admin.table("ngo_mobilization")\
        .select("*")\
        .eq("status", "active")\
        .order("created_at", desc=True)\
        .execute()
    return result.data

# --- Phase 6.5: Advanced Coordination ---

@router.post("/adopt-request/{request_id}")
async def adopt_victim_request(
    request_id: str,
    user=Depends(require_role("donor")),
    bg_tasks: BackgroundTasks = BackgroundTasks()
):
    """Direct Donor-to-Victim linking."""
    # 1. Verify existence and trust
    req = supabase_admin.table("resource_requests").select("*").eq("id", request_id).single().execute()
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
        "assigned_role": "donor"
    }
    result = supabase_admin.table("resource_requests").update(update_data).eq("id", request_id).execute()

    # 3. Log pulse
    bg_tasks.add_task(log_pulse, user["id"], "ADOPTED_REQUEST", request_id, 
                     f"Donor {user.get('full_name', 'Anonymous')} adopted verified request {request_id} for direct fulfillment.")
    
    return result.data[0]

class FeedbackBody(BaseModel):
    feedback: str = ""

@router.post("/complete-assignment/{assignment_id}")
async def complete_volunteer_assignment(
    assignment_id: str,
    body: FeedbackBody,
    user=Depends(require_role("volunteer")),
    bg_tasks: BackgroundTasks = BackgroundTasks()
):
    """Closes the loop between NGO mission and Volunteer action."""
    # 1. Update assignment
    update_data = {
        "status": "completed",
        "feedback_notes": body.feedback,
        "completed_at": datetime.now(timezone.utc).isoformat()
    }
    result = supabase_admin.table("volunteer_assignments")\
        .update(update_data)\
        .eq("id", assignment_id)\
        .eq("volunteer_id", user["id"])\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Assignment not found or unauthorized")

    # 2. Reward volunteer (Trust System)
    supabase_admin.rpc("increment_user_impact", {"user_id": user["id"], "points": 5}).execute()

    # 3. Log pulse
    bg_tasks.add_task(log_pulse, user["id"], "COMPLETED_ASSIGNMENT", assignment_id, 
                     f"Volunteer completed assigned mission task and earned impact points.")

    return result.data[0]

@router.get("/urgent-clusters")
async def get_urgent_clusters(user=Depends(require_role("ngo", "admin"))):
    """Spatial intelligence for NGOs to see where help is needed most."""
    result = supabase_admin.table("urgent_verification_clusters").select("*").execute()
    return result.data

@router.get("/my-impact")
async def get_my_impact(user=Depends(get_current_user)):
    """Personal motivation endpoint showing trust score and points."""
    result = supabase_admin.table("users").select("trust_score, total_impact_points, role")\
        .eq("id", user["id"]).single().execute()
    return result.data

# --- Phase 6.6: Deep Interaction ---

@router.get("/volunteer/profile", response_model=VolunteerProfile)
async def get_volunteer_profile(user=Depends(require_role("volunteer"))):
    result = supabase_admin.table("volunteer_profiles").select("*").eq("user_id", user["id"]).maybe_single().execute()
    if not result.data:
        # Auto-create if not exists
        profile = {"user_id": user["id"], "skills": [], "assets": [], "availability_status": "available"}
        result = supabase_admin.table("volunteer_profiles").insert(profile).execute()
    return result.data[0] if isinstance(result.data, list) else result.data

@router.patch("/volunteer/profile", response_model=VolunteerProfile)
async def update_volunteer_profile(data: VolunteerProfileUpdate, user=Depends(require_role("volunteer"))):
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = supabase_admin.table("volunteer_profiles").update(update_data).eq("user_id", user["id"]).execute()
    return result.data[0]

@router.post("/mission-tasks", response_model=MissionTask)
async def create_mission_task(data: MissionTaskCreate, user=Depends(require_role("ngo"))):
    task_data = {
        "id": str(uuid4()),
        "mobilization_id": data.mobilization_id,
        "task_description": data.task_description
    }
    result = supabase_admin.table("mission_tasks").insert(task_data).execute()
    return result.data[0]

@router.patch("/mission-tasks/{task_id}/complete")
async def complete_mission_task(task_id: str, user=Depends(require_role("volunteer", "ngo"))):
    update_data = {
        "is_completed": True,
        "completed_by": user["id"],
        "completed_at": datetime.now(timezone.utc).isoformat()
    }
    result = supabase_admin.table("mission_tasks").update(update_data).eq("id", task_id).execute()
    return result.data[0]

@router.post("/confirm-delivery/{request_id}")
async def confirm_aid_delivery(
    request_id: str, 
    code: str, 
    user=Depends(require_role("volunteer", "donor", "ngo")),
    bg_tasks: BackgroundTasks = BackgroundTasks()
):
    """Secure handshake using the 6-digit code from the victim."""
    # 1. Verify code
    req = supabase_admin.table("resource_requests").select("*").eq("id", request_id).single().execute()
    if not req.data:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if req.data.get("delivery_confirmation_code") != code.upper():
        # Small grace for case sensitivity handled by .upper()
        raise HTTPException(status_code=403, detail="Invalid confirmation code")

    # 2. Update status to completed
    update_data = {
        "status": "completed",
        "delivery_confirmed_at": datetime.now(timezone.utc).isoformat()
    }
    result = supabase_admin.table("resource_requests").update(update_data).eq("id", request_id).execute()

    # 3. Reward the deliverer
    supabase_admin.rpc("increment_user_impact", {"user_id": user["id"], "points": 10}).execute()

    bg_tasks.add_task(log_pulse, user["id"], "DELIVERED_AID", request_id, 
                     f"Deliverer successfully completed handshake for request {request_id}.")

    return {"message": "Delivery confirmed and points awarded", "request": result.data[0]}
