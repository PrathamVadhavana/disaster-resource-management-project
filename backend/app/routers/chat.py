from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.database import supabase_admin
from app.dependencies import security, supabase

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

def get_current_user_metadata(credentials = Depends(security)):
    try:
        resp = supabase.auth.get_user(credentials.credentials)
        if not resp or not resp.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = resp.user
        metadata = user.user_metadata or {}
        return {
            "id": str(user.id),
            "name": metadata.get("full_name", user.email),
            "role": metadata.get("role", "unknown")
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

@router.get("", response_model=List[ChatMessage])
async def get_messages(disaster_id: str, limit: int = 50, user: dict = Depends(get_current_user_metadata)):
    resp = supabase_admin.table("disaster_messages") \
        .select("*") \
        .eq("disaster_id", disaster_id) \
        .order("created_at", desc=False) \
        .limit(limit) \
        .execute()
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
    resp = supabase_admin.table("disaster_messages").insert(msg_data).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to post message")
    return resp.data[0]
