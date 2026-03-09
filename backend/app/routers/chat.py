from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.database import db_admin
from app.dependencies import security, _verify_supabase_token

router = APIRouter(prefix="/api/disasters/{disaster_id}/chat", tags=["Chat"])

class ChatMessageCreate(BaseModel):
    content: str

class ChatMessage(BaseModel):
    id: str
    disaster_id: str
    user_id: str
    user_name: str
    user_role: str
    content: str
    created_at: str

async def get_current_user_metadata(credentials = Depends(security)):
    try:
        decoded = _verify_supabase_token(credentials.credentials)
        uid = decoded["uid"]
        name = decoded.get("name") or decoded.get("email", "unknown")
        role = decoded.get("role", "unknown")

        # Fallback: look up name/role from the users table if not in claims
        if role == "unknown" or name == "unknown":
            try:
                db_resp = (
                    await db_admin.table("users")
                    .select("full_name, role")
                    .eq("id", uid)
                    .maybe_single()
                    .async_execute()
                )
                if db_resp.data:
                    if role == "unknown":
                        role = db_resp.data.get("role", role)
                    if name == "unknown" or name == decoded.get("email"):
                        name = db_resp.data.get("full_name") or name
            except Exception:
                pass

        return {
            "id": uid,
            "name": name,
            "role": role,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

@router.get("", response_model=List[ChatMessage])
async def get_messages(disaster_id: str, limit: int = 50, user: dict = Depends(get_current_user_metadata)):
    resp = await db_admin.table("disaster_messages") \
        .select("*") \
        .eq("disaster_id", disaster_id) \
        .order("created_at", desc=False) \
        .limit(limit) \
        .async_execute()
    return resp.data

@router.post("", response_model=ChatMessage)
async def post_message(disaster_id: str, payload: ChatMessageCreate, user: dict = Depends(get_current_user_metadata)):
    msg_data = {
        "disaster_id": disaster_id,
        "user_id": user["id"],
        "user_name": user["name"],
        "user_role": user["role"],
        "content": payload.content
    }
    resp = await db_admin.table("disaster_messages").insert(msg_data).async_execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to post message")
    return resp.data[0]
