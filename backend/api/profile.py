from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user_id, get_supabase

router = APIRouter()


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    timezone: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


@router.get("")
def get_profile(
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    r = (
        supabase.table("user_profiles")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = r.data or []
    if rows:
        return rows[0]
    # No profile yet; return defaults (client may save to create)
    return {
        "user_id": user_id,
        "display_name": "",
        "timezone": "UTC",
        "preferences": {},
    }


@router.put("")
def upsert_profile(
    body: ProfileUpdate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    data: dict = {"user_id": user_id, "updated_at": datetime.utcnow().isoformat()}
    if body.display_name is not None:
        data["display_name"] = body.display_name
    if body.timezone is not None:
        data["timezone"] = body.timezone
    if body.preferences is not None:
        data["preferences"] = body.preferences
    r = (
        supabase.table("user_profiles")
        .upsert(data, on_conflict="user_id")
        .execute()
    )
    if r.data:
        return r.data[0]
    return data
