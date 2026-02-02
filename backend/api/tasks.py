from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from enum import Enum

from api.deps import get_current_user_id, get_supabase

router = APIRouter()


class DifficultyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FocusLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TimePreference(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    FLEXIBLE = "flexible"


class TaskCreate(BaseModel):
    # Mandatory fields
    name: str
    difficulty: DifficultyLevel
    focus_level: FocusLevel
    deadline: str  # ISO datetime string
    # Optional fields
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
    time_preference: Optional[TimePreference] = None
    deadline: Optional[str] = None


@router.get("")
def list_tasks(user_id: str = Depends(get_current_user_id), supabase=Depends(get_supabase)):
    r = supabase.table("tasks").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return r.data


@router.post("")
def create_task(
    body: TaskCreate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    task_data = {
        "user_id": user_id,
        "name": body.name,
        "difficulty": body.difficulty.value,
        "focus_level": body.focus_level.value,
        "deadline": body.deadline,
        "status": "pending",
    }
    
    # Add optional fields if provided
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
    return r.data


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    supabase.table("tasks").delete().eq("id", task_id).eq("user_id", user_id).execute()
    return {"ok": True}
