from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from enum import Enum

from api.deps import get_current_user_id, get_supabase
from api.time_utils import parse_iso


def _minutes_between(start: str, end: str) -> int:
    try:
        s = parse_iso(start)
        e = parse_iso(end)
    except Exception:
        return 0
    delta = e - s
    return max(0, int(round(delta.total_seconds() / 60.0)))


def _approved_minutes_map(supabase, user_id: str) -> dict:
    res = (
        supabase.table("suggested_slots")
        .select("task_id,start_time,end_time")
        .eq("user_id", user_id)
        .eq("status", "approved")
        .execute()
    )
    totals: dict[str, int] = {}
    for row in res.data or []:
        task_id = row.get("task_id")
        if not task_id:
            continue
        minutes = _minutes_between(row.get("start_time"), row.get("end_time"))
        totals[task_id] = totals.get(task_id, 0) + minutes
    return totals

router = APIRouter()


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class FocusLevel(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class TimePreference(str, Enum):
    DAY = "day"
    MIDDAY = "midday"
    NIGHT = "night"


def _bucket_for_minutes(minutes: Optional[int]) -> FocusLevel:
    if minutes is None:
        return FocusLevel.MEDIUM
    if minutes <= 35:
        return FocusLevel.SHORT
    if minutes <= 70:
        return FocusLevel.MEDIUM
    return FocusLevel.LONG


class TaskCreate(BaseModel):
    name: str
    difficulty: DifficultyLevel
    focus_level: Optional[FocusLevel] = None
    focus_minutes: Optional[int] = None
    description: Optional[str] = None
    time_preference: Optional[TimePreference] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[DifficultyLevel] = None
    focus_level: Optional[FocusLevel] = None
    focus_minutes: Optional[int] = None
    time_preference: Optional[TimePreference] = None


@router.get("")
def list_tasks(user_id: str = Depends(get_current_user_id), supabase=Depends(get_supabase)):
    r = supabase.table("tasks").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    tasks = r.data or []
    if not tasks:
        return []
    approved_map = _approved_minutes_map(supabase, user_id)
    for t in tasks:
        approved = approved_map.get(t.get("id"), 0)
        estimated = t.get("estimated_minutes")
        t["approved_minutes"] = approved
        t["is_complete"] = bool(estimated is not None and approved >= estimated)
    return tasks


@router.post("")
def create_task(
    body: TaskCreate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    focus_minutes = body.focus_minutes
    focus_level = body.focus_level or _bucket_for_minutes(body.focus_minutes)

    task_data = {
        "user_id": user_id,
        "name": body.name,
        "difficulty": body.difficulty.value,
        "focus_level": focus_level.value,
    }

    if focus_minutes is not None:
        task_data["focus_minutes"] = max(10, min(int(focus_minutes), 240))
    if body.description is not None:
        task_data["description"] = body.description
    if body.time_preference is not None:
        task_data["time_preference"] = body.time_preference.value

    r = supabase.table("tasks").insert(task_data).execute()
    
    if not r.data:
        raise HTTPException(500, "Failed to create task")
    
    return r.data[0]


@router.get("/{task_id}")
def get_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    r = supabase.table("tasks").select("*").eq("id", task_id).eq("user_id", user_id).single().execute()
    if not r.data:
        raise HTTPException(404, "Task not found")
    task = r.data
    approved_map = _approved_minutes_map(supabase, user_id)
    approved = approved_map.get(task.get("id"), 0)
    estimated = task.get("estimated_minutes")
    task["approved_minutes"] = approved
    task["is_complete"] = bool(estimated is not None and approved >= estimated)
    task["focus_minutes"] = task.get("focus_minutes")
    task["focus_level"] = task.get("focus_level")
    return task


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    supabase.table("tasks").delete().eq("id", task_id).eq("user_id", user_id).execute()
    return {"ok": True}


@router.put("/{task_id}")
def update_task(
    task_id: str,
    body: TaskUpdate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.difficulty is not None:
        updates["difficulty"] = body.difficulty.value
    if body.focus_minutes is not None:
        updates["focus_minutes"] = max(10, min(int(body.focus_minutes), 240))
        updates["focus_level"] = _bucket_for_minutes(updates["focus_minutes"]).value
    elif body.focus_level is not None:
        updates["focus_level"] = body.focus_level.value
    if body.time_preference is not None:
        updates["time_preference"] = body.time_preference.value

    if not updates:
        return {"ok": True, "updated": 0}

    r = (
        supabase.table("tasks")
        .update(updates)
        .eq("id", task_id)
        .eq("user_id", user_id)
        .execute()
    )
    if r.data is None:
        raise HTTPException(404, "Task not found")
    return {"ok": True}
