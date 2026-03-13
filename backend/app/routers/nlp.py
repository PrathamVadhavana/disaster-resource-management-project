"""
NLP Triage & AI Chatbot Router — Phase 3
Endpoints for auto-classification, urgency extraction, and chatbot.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from datetime import datetime

from app.dependencies import _verify_supabase_token
from app.services.chatbot_service import (
    delete_session,
    get_session_data,
)
from app.services.chatbot_service import (
    process_message as chatbot_process_message,
)
from app.services.nlp_service import (
    classify_request,
    extract_urgency_signals,
    get_nlp_service,
)

# Try to use ML-based NLP service for better classification
try:
    from ml.nlp_service import extract_needs as ml_extract_needs
    from ml.nlp_service import predict_priority as ml_predict_priority

    _has_ml_nlp = True
except Exception:
    _has_ml_nlp = False

router = APIRouter()
security = HTTPBearer()


def _get_user_id(credentials: HTTPAuthorizationCredentials) -> str:
    """Extract and verify user from Supabase bearer token."""
    try:
        decoded = _verify_supabase_token(credentials.credentials)
        return decoded["uid"]
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


# ── Request / Response models ──────────────────────────────────────────────────


class ClassifyRequest(BaseModel):
    description: str = Field(..., min_length=3, max_length=5000, description="Free-text request description")
    priority: str = Field("medium", description="User-selected priority (may be escalated)")
    resource_type: str | None = Field(None, description="User-selected resource type (optional)")


class ClassifyResponse(BaseModel):
    resource_types: list[str]
    resource_type_scores: dict
    recommended_priority: str
    priority_confidence: float
    original_priority: str | None
    priority_was_escalated: bool
    estimated_quantity: int
    urgency_signals: list[dict]
    confidence: float
    urgency_score: float | None = None
    urgency_method: str | None = None


class UrgencyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class UrgencySignalResponse(BaseModel):
    keyword: str
    label: str
    severity_boost: int


class ChatRequest(BaseModel):
    session_id: str | None = Field(None, description="Existing session ID to continue conversation")
    message: str = Field(..., min_length=1, max_length=2000, description="User message")


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    extracted_data: dict | None = None
    request_ready: bool = False
    message_count: int = 0


class OverrideRequest(BaseModel):
    """Admin override of NLP classification — feeds back for training."""

    request_id: str
    corrected_resource_type: str | None = None
    corrected_priority: str | None = None
    corrected_quantity: int | None = None
    override_reason: str | None = None


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
    Uses ML-based DistilBERT when available, falls back to rule-based NLP.
    """
    _get_user_id(credentials)  # auth check

    # Try ML-based classification first for better accuracy
    if _has_ml_nlp:
        try:
            ml_priority = ml_predict_priority(body.description)
            ml_needs = ml_extract_needs(body.description)
            resource_types = [n["type"] for n in ml_needs] if ml_needs else []
            urgency_signals = extract_urgency_signals(body.description)

            was_escalated = False
            if body.priority and ml_priority["priority"] != body.priority:
                priority_order = ["low", "medium", "high", "critical"]
                if priority_order.index(ml_priority["priority"]) > priority_order.index(body.priority):
                    was_escalated = True

            return JSONResponse(
                content={
                    "resource_types": resource_types or ([body.resource_type] if body.resource_type else []),
                    "resource_type_scores": {},
                    "recommended_priority": ml_priority["priority"],
                    "priority_confidence": ml_priority["confidence"],
                    "original_priority": body.priority,
                    "priority_was_escalated": was_escalated,
                    "estimated_quantity": ml_needs[0]["quantity"] if ml_needs else 1,
                    "urgency_signals": [
                        {"keyword": s.keyword, "label": s.label, "severity_boost": s.severity_boost}
                        for s in urgency_signals
                    ],
                    "confidence": ml_priority["confidence"],
                }
            )
        except Exception:
            pass  # Fall through to rule-based

    result = classify_request(
        description=body.description,
        user_priority=body.priority,
        user_resource_type=body.resource_type,
    )
    
    # Get urgency score from ML model (or rule-based fallback)
    nlp_service = get_nlp_service()
    urgency_score, urgency_method = nlp_service.get_urgency_score(body.description)
    
    # Add urgency score to result
    result_dict = result.to_dict()
    result_dict["urgency_score"] = round(urgency_score, 3)
    result_dict["urgency_method"] = urgency_method
    
    return JSONResponse(content=result_dict)


@router.post("/extract-urgency", response_model=list[UrgencySignalResponse])
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
    return JSONResponse(
        content=[{"keyword": s.keyword, "label": s.label, "severity_boost": s.severity_boost} for s in signals]
    )


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
    # Mark request_ready when conversation reaches the confirmation or submitted stage —
    # the frontend shows a structured submit button at that point.
    state = result.get("state", "")
    return JSONResponse(
        content={
            "session_id": result["session_id"],
            "assistant_message": result["message"],
            "extracted_data": result.get("extracted_data"),
            "request_ready": state in ("confirm", "submitted"),
            "message_count": 0,
        }
    )


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
    Admin override of NLP classification.
    Stores the correction for future training data.
    Triggers automatic retraining after every 50 new feedback rows.
    """
    user_id = _get_user_id(credentials)

    from app.database import db_admin

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
            await db_admin.table("resource_requests").update(update_fields).eq("id", body.request_id).async_execute()

        # Log the override for training
        feedback_created = False
        try:
            await db_admin.table("nlp_training_feedback").insert(override_data).async_execute()
            feedback_created = True
        except Exception as e:
            # Table may not exist yet — log but don't fail
            print(f"⚠️  Could not log NLP feedback (table may not exist): {e}")

        # Check if we should trigger automatic retraining
        retrain_triggered = False
        retrain_result = None
        if feedback_created:
            try:
                # Count unused feedback rows
                count_response = await db_admin.table("nlp_training_feedback").select("id", count="exact").eq("used_in_training", False).execute()
                unused_count = count_response.count or 0
                
                # Trigger retraining if we've crossed the threshold
                if unused_count >= 50:
                    nlp_service = get_nlp_service()
                    retrain_result = await nlp_service.retrain_from_feedback()
                    retrain_triggered = True
                    print(f"🔄 Automatic retraining triggered: {retrain_result}")
            except Exception as e:
                print(f"⚠️  Could not check feedback count or trigger retraining: {e}")

        response_content = {
            "message": "Override applied",
            "updated_fields": update_fields
        }
        
        if retrain_triggered and retrain_result:
            response_content["retrain_triggered"] = True
            response_content["retrain_result"] = retrain_result

        return JSONResponse(content=response_content)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying override: {str(e)}")


# ── Retraining Endpoint ─────────────────────────────────────────────────────────


class RetrainResponse(BaseModel):
    success: bool
    rows_used: int | None = None
    resource_type_accuracy: float | None = None
    priority_accuracy: float | None = None
    timestamp: str
    error: str | None = None


@router.post("/retrain", response_model=RetrainResponse)
async def retrain_nlp_models(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Admin-only endpoint to retrain NLP classification models from feedback data.
    Uses TF-IDF + LogisticRegression pipelines for resource type and priority classification.
    
    Requires admin authentication. Returns model accuracy on test split.
    """
    # Verify admin role
    from app.dependencies import _verify_supabase_token
    try:
        decoded = _verify_supabase_token(credentials.credentials)
        # Check if user is admin (you may need to adjust this based on your auth setup)
        user_id = decoded.get("uid")
        
        # Get user role from database
        from app.database import db_admin
        user_response = await db_admin.table("users").select("role").eq("id", user_id).execute()
        if not user_response.data or user_response.data[0].get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

    # Perform retraining
    nlp_service = get_nlp_service()
    result = await nlp_service.retrain_from_feedback()
    
    return JSONResponse(content=result)


# ── Urgency Model Building Endpoint ─────────────────────────────────────────────


class BuildUrgencyResponse(BaseModel):
    success: bool
    rows_used: int | None = None
    mse: float | None = None
    r2_score: float | None = None
    timestamp: str
    error: str | None = None


class UrgencyScoreRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000)
    created_at: str | None = Field(None, description="ISO timestamp of request creation")


class UrgencyScoreResponse(BaseModel):
    urgency_score: float
    method: str


@router.post("/build-urgency-model", response_model=BuildUrgencyResponse)
async def build_urgency_model(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Admin-only endpoint to build ML-based urgency scoring model.
    
    Queries resource_requests joined with request_verifications,
    filters by verification_status in ('trusted', 'false_alarm', 'dubious'),
    and trains a GradientBoostingClassifier.
    
    Features: TF-IDF of description, character count, exclamation marks count,
    question marks count, keyword match scores, hour of day of submission.
    
    Labels (soft): 1.0 if 'trusted', 0.0 if 'false_alarm', 0.5 if 'dubious'.
    
    Requires admin authentication. Returns model metrics.
    """
    # Verify admin role
    from app.dependencies import _verify_supabase_token
    try:
        decoded = _verify_supabase_token(credentials.credentials)
        user_id = decoded.get("uid")
        
        # Get user role from database
        from app.database import db_admin
        user_response = await db_admin.table("users").select("role").eq("id", user_id).execute()
        if not user_response.data or user_response.data[0].get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

    # Build the urgency model
    nlp_service = get_nlp_service()
    result = await nlp_service.build_urgency_model()
    
    return JSONResponse(content=result)


@router.post("/urgency-score", response_model=UrgencyScoreResponse)
async def get_urgency_score(
    body: UrgencyScoreRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Get urgency score (0-1) for a request description.
    
    Uses ML model if available, otherwise falls back to rule-based.
    Returns the score and the method used ('ml_model' or 'rule_based').
    """
    _get_user_id(credentials)
    
    # Parse created_at if provided
    created_at = None
    if body.created_at:
        try:
            created_at = datetime.fromisoformat(body.created_at.replace("Z", "+00:00"))
        except:
            pass
    
    nlp_service = get_nlp_service()
    score, method = nlp_service.get_urgency_score(body.description, created_at)
    
    return JSONResponse(content={
        "urgency_score": round(score, 3),
        "method": method
    })
