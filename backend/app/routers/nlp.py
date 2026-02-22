"""
NLP Triage & AI Chatbot Router — Phase 3
Endpoints for auto-classification, urgency extraction, and chatbot.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List

from app.database import supabase
from app.services.nlp_service import (
    classify_request,
    extract_urgency_signals,
    ClassificationResult,
)
from app.services.chatbot_service import (
    process_message as chatbot_process_message,
    get_session_data,
    delete_session,
)

router = APIRouter()
security = HTTPBearer()


def _get_user_id(credentials: HTTPAuthorizationCredentials) -> str:
    """Extract and verify user from bearer token."""
    try:
        user = supabase.auth.get_user(credentials.credentials)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


# ── Request / Response models ──────────────────────────────────────────────────

class ClassifyRequest(BaseModel):
    description: str = Field(..., min_length=3, max_length=5000, description="Free-text request description")
    priority: str = Field("medium", description="User-selected priority (may be escalated)")
    resource_type: Optional[str] = Field(None, description="User-selected resource type (optional)")


class ClassifyResponse(BaseModel):
    resource_types: List[str]
    resource_type_scores: dict
    recommended_priority: str
    priority_confidence: float
    original_priority: Optional[str]
    priority_was_escalated: bool
    estimated_quantity: int
    urgency_signals: List[dict]
    confidence: float


class UrgencyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class UrgencySignalResponse(BaseModel):
    keyword: str
    label: str
    severity_boost: int


class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Existing session ID to continue conversation")
    message: str = Field(..., min_length=1, max_length=2000, description="User message")


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    extracted_data: Optional[dict] = None
    request_ready: bool = False
    message_count: int = 0


class OverrideRequest(BaseModel):
    """Coordinator override of NLP classification — feeds back for training."""
    request_id: str
    corrected_resource_type: Optional[str] = None
    corrected_priority: Optional[str] = None
    corrected_quantity: Optional[int] = None
    override_reason: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/classify", response_model=ClassifyResponse)
def classify_text(
    body: ClassifyRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Auto-classify a victim request description.
    Returns resource type, priority recommendation, quantity estimate,
    and urgency signals with confidence scores.
    Uses rule-based NLP with keyword/phrase analysis.
    """
    _get_user_id(credentials)  # auth check

    result = classify_request(
        description=body.description,
        user_priority=body.priority,
        user_resource_type=body.resource_type,
    )
    return JSONResponse(content=result.to_dict())


@router.post("/extract-urgency", response_model=List[UrgencySignalResponse])
async def extract_urgency(
    body: UrgencyRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Extract urgency signals from text using NER-style keyword detection.
    Returns labeled signals with severity boost values.
    """
    _get_user_id(credentials)

    signals = extract_urgency_signals(body.text)
    return JSONResponse(content=[
        {"keyword": s.keyword, "label": s.label, "severity_boost": s.severity_boost}
        for s in signals
    ])


@router.post("/chatbot", response_model=ChatResponse)
def chatbot_endpoint(
    body: ChatRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    AI Victim Chatbot — rule-based conversational intake assistant.
    Send a message and get a guided response.
    When enough info is gathered, returns extracted_data + request_ready=true.
    """
    _get_user_id(credentials)  # auth check

    result = chatbot_process_message(
        session_id=body.session_id,
        user_message=body.message,
    )

    # Map to ChatResponse shape
    return JSONResponse(content={
        "session_id": result["session_id"],
        "assistant_message": result["message"],
        "extracted_data": result.get("extracted_data"),
        "request_ready": result.get("state") == "submitted",
        "message_count": 0,
    })


@router.get("/chatbot/{session_id}")
async def get_chat_session(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get the current state of a chatbot session."""
    _get_user_id(credentials)

    data = get_session_data(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return JSONResponse(content=data)


@router.delete("/chatbot/{session_id}")
async def end_chat_session(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """End and delete a chatbot session."""
    _get_user_id(credentials)
    delete_session(session_id)
    return {"message": "Session ended"}


@router.post("/override")
async def override_classification(
    body: OverrideRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Coordinator override of NLP classification.
    Stores the correction for future training data.
    """
    user_id = _get_user_id(credentials)

    from app.database import supabase_admin

    # Store the override as training feedback
    try:
        override_data = {
            "request_id": body.request_id,
            "corrected_by": user_id,
            "corrected_resource_type": body.corrected_resource_type,
            "corrected_priority": body.corrected_priority,
            "corrected_quantity": body.corrected_quantity,
            "override_reason": body.override_reason,
        }

        # Update the request itself if corrections provided
        update_fields = {}
        if body.corrected_resource_type:
            update_fields["resource_type"] = body.corrected_resource_type
        if body.corrected_priority:
            update_fields["priority"] = body.corrected_priority
        if body.corrected_quantity:
            update_fields["quantity"] = body.corrected_quantity

        if update_fields:
            # Also mark that NLP was overridden
            update_fields["nlp_overridden"] = True
            supabase_admin.table("resource_requests").update(
                update_fields
            ).eq("id", body.request_id).execute()

        # Log the override for training
        try:
            supabase_admin.table("nlp_training_feedback").insert(override_data).execute()
        except Exception as e:
            # Table may not exist yet — log but don't fail
            print(f"⚠️  Could not log NLP feedback (table may not exist): {e}")

        return JSONResponse(content={"message": "Override applied", "updated_fields": update_fields})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying override: {str(e)}")
