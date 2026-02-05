from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user_id, get_supabase

router = APIRouter()


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    timezone: Optional[str] = None
    # legacy structured prefs (kept for compatibility)
    preferences: Optional[Dict[str, Any]] = None
    # new free-text preferences
    preferences_text: Optional[str] = None


@router.get("")
def get_profile(
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    profile_r = (
        supabase.table("user_profiles")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    profile = (profile_r.data or [None])[0]

    # Detect calendar connection
    cal_r = (
        supabase.table("calendar_tokens")
        .select("user_id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    calendar_connected = bool(cal_r.data)

    if profile:
        if calendar_connected:
            profile["timezone"] = None  # ignore stored timezone if calendar is connected
        profile["calendar_connected"] = calendar_connected
        # ensure text key is present for frontend
        if "preferences_text" not in profile:
            profile["preferences_text"] = profile.get("preferences") or ""
        return profile

    # No profile yet; return defaults
    return {
        "user_id": user_id,
        "display_name": "",
        "timezone": None if calendar_connected else "",
        "preferences": {},
        "preferences_text": "",
        "calendar_connected": calendar_connected,
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
        # Only store timezone if not connected to calendar (calendar will provide tz)
        cal_r = (
            supabase.table("calendar_tokens")
            .select("user_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        calendar_connected = bool(cal_r.data)
        if not calendar_connected:
            data["timezone"] = body.timezone
    if body.preferences is not None:
        data["preferences"] = body.preferences
    if body.preferences_text is not None:
        data["preferences_text"] = body.preferences_text
    r = (
        supabase.table("user_profiles")
        .upsert(data, on_conflict="user_id")
        .execute()
    )
    if r.data:
        return r.data[0]
    return data
