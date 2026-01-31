from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_current_user_id, get_supabase

router = APIRouter()


class TaskCreate(BaseModel):
    name: str
    description: str = ""
    difficulty: str  # easy | medium | hard
    focus_level: str  # short | medium | long
    time_preference: str  # day | midday | night


class TaskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    difficulty: str | None = None
    focus_level: str | None = None
    time_preference: str | None = None


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
    r = (
        supabase.table("tasks")
        .insert(
            {
                "user_id": user_id,
                "name": body.name,
                "description": body.description,
                "difficulty": body.difficulty,
                "focus_level": body.focus_level,
                "time_preference": body.time_preference,
            }
        )
        .execute()
    )
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
