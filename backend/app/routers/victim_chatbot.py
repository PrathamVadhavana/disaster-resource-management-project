"""
Victim AI Chatbot Router — Groq-Powered Intake Assistant
=========================================================
Provides AI-powered conversational intake for victims to request resources.
Uses Groq API for intelligent natural language understanding.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from app.database import db_admin
from app.dependencies import _verify_supabase_token
from app.services.chatbot_service import (
    SmartDefaultsResult,
    UrgencyContextResult,
    delete_session,
    get_session_data,
    get_smart_defaults,
    get_urgency_context,
    log_chatbot_session,
    process_message as chatbot_process_message,
)

logger = logging.getLogger("victim_chatbot_router")

router = APIRouter(prefix="/api/victim/chatbot", tags=["Victim AI Chatbot"])
security = HTTPBearer()


def _get_user(credentials) -> dict:
    """Extract and verify user from Supabase bearer token."""
    try:
        decoded = _verify_supabase_token(credentials.credentials)
        return {
            "id": decoded.get("uid"),
            "email": decoded.get("email"),
            "role": decoded.get("role", "victim"),
            "name": decoded.get("name", decoded.get("email", "Unknown")),
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


# ── Request / Response Models ──────────────────────────────────────────────────


class ChatRequest(BaseModel):
    session_id: str | None = Field(None, description="Existing session ID to continue conversation")
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    latitude: float | None = Field(None, description="User's GPS latitude")
    longitude: float | None = Field(None, description="User's GPS longitude")


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    extracted_data: dict | None = None
    request_ready: bool = False
    message_count: int = 0
    smart_defaults: dict | None = None
    urgency_context: dict | None = None
    metadata: dict | None = None

class SessionDataResponse(BaseModel):
    session_id: str
    extracted_data: dict
    state: str


class SubmitRequestPayload(BaseModel):
    session_id: str
    resource_type: str
    quantity: int = 1
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    address_text: str | None = None
    people_count: int = 1
    has_medical_needs: bool = False
    medical_details: str | None = None
    priority: str = "medium"


class SubmitResponse(BaseModel):
    success: bool
    request_id: str | None = None
    message: str
    request_data: dict | None = None


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/message", response_model=ChatResponse)
async def chat_message(
    body: ChatRequest,
    credentials=Depends(security),
):
    """
    Send a message to the AI victim chatbot.
    The chatbot guides victims through structured resource request creation using Groq AI.
    """
    user = _get_user(credentials)
    user_id = user["id"]

    logger.info("Chatbot message from user=%s session=%s: %.80s...", user_id, body.session_id or "new", body.message)

    # Process the message through the chatbot service
    result = chatbot_process_message(
        session_id=body.session_id,
        user_message=body.message,
    )

    # Map to ChatResponse shape
    state = result.get("state", "")
    extracted_data = result.get("extracted_data")

    # Get smart defaults and urgency context if location provided
    smart_defaults = None
    urgency_context = None

    if body.latitude and body.longitude:
        try:
            # Get smart defaults based on area
            defaults = await get_smart_defaults((body.latitude, body.longitude))
            if defaults.has_data:
                smart_defaults = {
                    "top_resources": defaults.top_resource_types,
                    "message": defaults.area_message,
                }

            # Check for active disasters nearby
            urgency = await get_urgency_context((body.latitude, body.longitude))
            if urgency.has_active_disaster:
                urgency_context = {
                    "has_disaster": True,
                    "disaster_type": urgency.disaster_type,
                    "disaster_title": urgency.disaster_title,
                    "message": urgency.urgency_message,
                    "priority_boost": urgency.priority_boost,
                }
        except Exception as e:
            logger.warning(f"Failed to get smart defaults/urgency context: {e}")

    # Mark request_ready when conversation reaches the confirmation or submitted stage
    request_ready = state in ("confirm", "submitted")

    return JSONResponse(
        content={
            "session_id": result["session_id"],
            "assistant_message": result["message"],
            "extracted_data": extracted_data,
            "request_ready": request_ready,
            "message_count": len(result.get("metadata", {})),
            "smart_defaults": smart_defaults,
            "urgency_context": urgency_context,
            "metadata": result.get("metadata", {}),
        }
    )


@router.get("/session/{session_id}", response_model=SessionDataResponse)
async def get_session(
    session_id: str,
    credentials=Depends(security),
):
    """Get the current state of a chatbot session."""
    _get_user(credentials)

    data = get_session_data(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")

    return JSONResponse(
        content={
            "session_id": session_id,
            "extracted_data": data,
            "state": "active",
        }
    )


@router.delete("/session/{session_id}")
async def end_session(
    session_id: str,
    credentials=Depends(security),
):
    """End and delete a chatbot session."""
    _get_user(credentials)

    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"message": "Session ended successfully", "session_id": session_id}


@router.post("/submit", response_model=SubmitResponse)
async def submit_request(
    body: SubmitRequestPayload,
    credentials=Depends(security),
):
    """
    Submit a resource request from the chatbot conversation.
    Creates a formal resource request in the database.
    """
    user = _get_user(credentials)
    user_id = user["id"]

    logger.info("Submitting chatbot request for user=%s session=%s: %s", user_id, body.session_id, body.resource_type)

    try:
        # Build the request data
        insert_data = {
            "victim_id": user_id,
            "resource_type": body.resource_type,
            "quantity": body.quantity,
            "priority": body.priority,
            "status": "pending",
            "description": body.description or f"Request submitted via AI chatbot",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "source": "chatbot",
        }

        if body.latitude is not None:
            insert_data["latitude"] = body.latitude
        if body.longitude is not None:
            insert_data["longitude"] = body.longitude
        if body.address_text:
            insert_data["address_text"] = body.address_text
        if body.people_count > 1:
            insert_data["people_count"] = body.people_count
        if body.has_medical_needs:
            insert_data["has_medical_needs"] = True
            insert_data["medical_details"] = body.medical_details or ""
            if body.priority not in ("critical", "high"):
                insert_data["priority"] = "high"

        # Insert into database
        response = await db_admin.table("resource_requests").insert(insert_data).execute()

        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create request")

        request_row = response.data[0]
        request_id = request_row.get("id")

        # Log the completed session
        try:
            await log_chatbot_session(
                session_id=body.session_id,
                user_id=user_id,
                states_visited=["greeting", "ask_situation", "confirm", "submitted"],
                final_resource_type=body.resource_type,
                final_priority=body.priority,
                completion_status="completed",
            )
        except Exception as e:
            logger.warning(f"Failed to log chatbot session: {e}")

        # Clean up the session
        delete_session(body.session_id)

        return JSONResponse(
            content={
                "success": True,
                "request_id": request_id,
                "message": f"Your request for {body.resource_type} has been submitted successfully! A relief team will review it shortly.",
                "request_data": {
                    "id": request_id,
                    "resource_type": body.resource_type,
                    "quantity": body.quantity,
                    "priority": body.priority,
                    "status": "pending",
                },
            },
            status_code=201,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit chatbot request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit request: {str(e)}")


@router.get("/smart-defaults")
async def get_area_smart_defaults(
    latitude: float,
    longitude: float,
    credentials=Depends(security),
):
    """
    Get smart resource suggestions based on the user's location.
    Returns the most commonly requested resources in their area.
    """
    _get_user(credentials)

    try:
        defaults = await get_smart_defaults((latitude, longitude))
        return JSONResponse(
            content={
                "top_resources": defaults.top_resource_types,
                "message": defaults.area_message,
                "has_data": defaults.has_data,
            }
        )
    except Exception as e:
        logger.error(f"Failed to get smart defaults: {e}")
        raise HTTPException(status_code=500, detail="Failed to get smart defaults")


@router.get("/urgency-context")
async def get_area_urgency_context(
    latitude: float,
    longitude: float,
    credentials=Depends(security),
):
    """
    Check for active disasters near the user's location.
    Returns disaster information and priority boost if applicable.
    """
    _get_user(credentials)

    try:
        urgency = await get_urgency_context((latitude, longitude))
        return JSONResponse(
            content={
                "has_disaster": urgency.has_active_disaster,
                "disaster_type": urgency.disaster_type,
                "disaster_title": urgency.disaster_title,
                "message": urgency.urgency_message,
                "priority_boost": urgency.priority_boost,
            }
        )
    except Exception as e:
        logger.error(f"Failed to get urgency context: {e}")
        raise HTTPException(status_code=500, detail="Failed to get urgency context")