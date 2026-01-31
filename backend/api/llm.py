import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai import OpenAI

from api.calendar import get_busy
from api.deps import get_current_user_id, get_supabase
from api.time_utils import parse_iso
from config import settings

router = APIRouter()


class PlanRequest(BaseModel):
    task: str
    preferences: dict | None = None
    start: str | None = None
    end: str | None = None


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


def _client():
    if not settings.openai_api_key:
        raise HTTPException(500, "OpenAI API key not configured")
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        raise HTTPException(500, "OpenAI SDK not installed. Run: pip install -r backend/requirements.txt")
    return OpenAI(api_key=settings.openai_api_key)


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
    prefs = body.preferences if body.preferences is not None else profile.get("preferences") or {}

    busy = get_busy(user_id, supabase, start_dt.isoformat(), end_dt.isoformat())
    free_blocks = _free_blocks_from_busy(busy, start_dt, end_dt)

    payload = {
        "task": body.task,
        "preferences": prefs,
        "user_profile": {
            "display_name": profile.get("display_name"),
            "timezone": profile.get("timezone") or "UTC",
        },
        "free_time_blocks": free_blocks,
    }

    system = (
        "You are a scheduling assistant. Use the user's task, preferences, and free time blocks to "
        "estimate total minutes and propose an efficient time-block plan. Respond with JSON only: "
        "{total_estimated_minutes: int, blocks: [{start: string, end: string, duration_minutes: int, reason: string}], notes: string}."
    )

    client = _client()
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
        temperature=0.2,
    )

    content = resp.choices[0].message.content or ""
    try:
        plan = json.loads(content)
    except Exception:
        plan = {"raw": content}

    return {
        "plan": plan,
        "free_time_blocks": free_blocks,
    }
