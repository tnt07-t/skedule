import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.calendar import get_busy
from api.deps import get_current_user_id, get_supabase
from api.time_utils import parse_iso
from config import settings

router = APIRouter()


class PlanRequest(BaseModel):
    task: str
    task_id: Optional[str] = None
    # legacy structured preferences (JSON) kept for compatibility
    preferences: Optional[dict] = None
    # new free-text preferences
    preferences_text: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


def _merge_busy(busy: list) -> list[tuple[datetime, datetime]]:
    intervals = sorted((parse_iso(b["start"]), parse_iso(b["end"])) for b in busy)
    merged: list[tuple[datetime, datetime]] = []
    for s, e in intervals:
        if not merged or s > merged[-1][1]:
            merged.append((s, e))
        else:
            last_s, last_e = merged[-1]
            if e > last_e:
                merged[-1] = (last_s, e)
    return merged


def _free_blocks_from_busy(busy: list, start_dt: datetime, end_dt: datetime) -> list[dict]:
    if not busy:
        return [{"start": start_dt.isoformat(), "end": end_dt.isoformat()}]
    free: list[dict] = []
    merged = _merge_busy(busy)
    cursor = start_dt
    for s, e in merged:
        if s > cursor:
            free.append({"start": cursor.isoformat(), "end": s.isoformat()})
        if e > cursor:
            cursor = e
    if cursor < end_dt:
        free.append({"start": cursor.isoformat(), "end": end_dt.isoformat()})
    return free


def _coerce_minutes(value) -> Optional[int]:
    if value is None:
        return None
    try:
        minutes = int(float(value))
    except Exception:
        return None
    if minutes < 0:
        return None
    return minutes


def _client():
    if not settings.gemini_api_key:
        raise HTTPException(500, "Gemini API key not configured")
    try:
        import google.generativeai as genai  # type: ignore
    except Exception:
        raise HTTPException(500, "Gemini SDK not installed. Run: pip install -r backend/requirements.txt")
    genai.configure(api_key=settings.gemini_api_key)
    model_name = settings.gemini_model or "gemini-1.5-pro"
    return genai.GenerativeModel(model_name)


@router.post("")
def plan_task(
    body: PlanRequest,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    start_dt = parse_iso(body.start) if body.start else datetime.now(timezone.utc)
    end_dt = parse_iso(body.end) if body.end else (start_dt + timedelta(days=7))
    max_end = start_dt + timedelta(days=7)
    if end_dt > max_end:
        end_dt = max_end
    if end_dt <= start_dt:
        raise HTTPException(400, "end must be after start")

    profile_r = (
        supabase.table("user_profiles")
        .select("*")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    profile = profile_r.data or {}
    task_record = None
    if body.task_id:
        try:
            task_r = (
                supabase.table("tasks")
                .select("id,name,description,difficulty,focus_level,time_preference,estimated_minutes")
                .eq("id", body.task_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as e:
            if "estimated_minutes" in str(e):
                raise HTTPException(500, "DB migration missing: run 004_task_estimated_minutes.sql") from e
            raise
        if not task_r.data:
            raise HTTPException(404, "Task not found")
        task_record = task_r.data[0]
    prefs_structured = (
        body.preferences
        if body.preferences is not None
        else profile.get("preferences")
        or {}
    )
    prefs_text = (
        body.preferences_text
        if body.preferences_text is not None
        else profile.get("preferences_text")
        or ""
    )

    busy = get_busy(user_id, supabase, start_dt.isoformat(), end_dt.isoformat())
    free_blocks = _free_blocks_from_busy(busy, start_dt, end_dt)

    payload = {
        "task": body.task,
        "task_record": task_record,
        "preferences_structured": prefs_structured,
        "preferences_text": prefs_text,
        "user_profile": {
            "display_name": profile.get("display_name"),
            "timezone": profile.get("timezone") or "UTC",
        },
        "free_time_blocks": free_blocks,
    }

    system = (
        "You are a scheduling assistant. Use the user's task, preferences (both structured JSON and free-text), "
        "and free time blocks to estimate total minutes and propose an efficient time-block plan. "
        "Interpret free-text preferences creatively (e.g., 'no Fridays', 'prefer mornings', 'deep work before lunch'). "
        "Respond with JSON only: "
        "{total_estimated_minutes: int, blocks: [{start: string, end: string, duration_minutes: int, reason: string}], notes: string}."
    )

    client = _client()
    try:
        resp = client.generate_content(
            [
                {"role": "system", "parts": [system]},
                {"role": "user", "parts": [json.dumps(payload)]},
            ],
            generation_config={"temperature": 0.2},
        )
    except Exception as e:
        raise HTTPException(500, f"Gemini request failed: {e}") from e

    content = getattr(resp, "text", "") or ""
    try:
        plan = json.loads(content)
    except Exception:
        plan = {"raw": content}

    estimated_minutes = None
    if isinstance(plan, dict):
        estimated_minutes = _coerce_minutes(plan.get("total_estimated_minutes"))
        if estimated_minutes is not None and body.task_id:
            supabase.table("tasks").update(
                {"estimated_minutes": estimated_minutes}
            ).eq("id", body.task_id).eq("user_id", user_id).execute()

    return {
        "plan": plan,
        "free_time_blocks": free_blocks,
        "estimated_minutes": estimated_minutes,
    }
