"""Suggest time blocks from free-busy and task prefs; approve/reject."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_current_user_id, get_supabase
from api.time_utils import clamp_range, parse_iso
from api.calendar import get_calendar_service, get_busy

router = APIRouter()

# Block lengths in minutes by focus_level
FOCUS_MINUTES = {"short": 25, "medium": 50, "long": 90}
# Preferred hour ranges (UTC) by time_preference: (start_hour, end_hour)
PREF_HOURS = {"day": (9, 12), "midday": (12, 17), "night": (17, 23)}


def slots_from_busy(busy: list, start_dt: datetime, end_dt: datetime, duration_min: int):
    """Chop [start_dt, end_dt] into free slots of at least duration_min, avoiding busy."""
    free_slots = []
    busy_sorted = sorted(
        (parse_iso(b["start"]), parse_iso(b["end"])) for b in busy
    )
    t = start_dt
    bi = 0
    while t < end_dt:
        slot_end = t + timedelta(minutes=duration_min)
        if slot_end > end_dt:
            break
        # skip past any busy that ends before t
        while bi < len(busy_sorted) and busy_sorted[bi][1] <= t:
            bi += 1
        # if next busy starts before our slot ends, we can't use this slot
        if bi < len(busy_sorted) and busy_sorted[bi][0] < slot_end:
            t = busy_sorted[bi][1]
            continue
        free_slots.append((t.isoformat(), slot_end.isoformat()))
        t = slot_end
    return free_slots


@router.post("/suggest/{task_id}")
def suggest_slots(
    task_id: str,
    start: str,
    end: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Compute suggested slots for task and save; return suggestions."""
    # Get task
    tr = supabase.table("tasks").select("*").eq("id", task_id).eq("user_id", user_id).single().execute()
    if not tr.data:
        raise HTTPException(404, "Task not found")
    task = tr.data
    duration_min = FOCUS_MINUTES.get(task["focus_level"], 50)
    pref = task.get("time_preference", "midday")
    h_start, h_end = PREF_HOURS.get(pref, (12, 17))

    start_dt, end_dt = clamp_range(start, end)
    # Narrow to preferred hours on each day
    candidates = []
    d = start_dt.date()
    while d <= end_dt.date():
        day_start = datetime(d.year, d.month, d.day, h_start, 0, 0, tzinfo=start_dt.tzinfo)
        day_end = datetime(d.year, d.month, d.day, h_end, 0, 0, tzinfo=start_dt.tzinfo)
        if day_start < start_dt:
            day_start = start_dt
        if day_end > end_dt:
            day_end = end_dt
        if day_start < day_end:
            candidates.append((day_start, day_end))
        d += timedelta(days=1)

    all_busy = []
    for cs, ce in candidates:
        all_busy.extend(
            get_busy(user_id, supabase, cs.isoformat(), ce.isoformat())
        )

    suggestions_list = []
    for cs, ce in candidates:
        for s_start, s_end in slots_from_busy(all_busy, cs, ce, duration_min):
            r = (
                supabase.table("suggested_slots")
                .insert(
                    {
                        "task_id": task_id,
                        "user_id": user_id,
                        "start_time": s_start,
                        "end_time": s_end,
                        "status": "pending",
                    }
                )
                .execute()
            )
            suggestions_list.append(r.data[0])

    return suggestions_list


@router.get("")
def list_suggestions(
    task_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    q = supabase.table("suggested_slots").select("*").eq("user_id", user_id)
    if task_id:
        q = q.eq("task_id", task_id)
    r = q.order("start_time").execute()
    return r.data


class ApproveBody(BaseModel):
    add_to_calendar: bool = True


@router.post("/{suggestion_id}/approve")
def approve_slot(
    suggestion_id: str,
    body: ApproveBody = ApproveBody(),
  user_id: str = Depends(get_current_user_id),
  supabase=Depends(get_supabase),
):
    r = (
        supabase.table("suggested_slots")
        .select("*")
        .eq("id", suggestion_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not r.data:
        raise HTTPException(404, "Suggestion not found")
    slot = r.data
    if slot["status"] != "pending":
        raise HTTPException(400, "Already processed")
    supabase.table("suggested_slots").update({"status": "approved"}).eq("id", suggestion_id).execute()
    if body.add_to_calendar:
        task_r = supabase.table("tasks").select("name, description").eq("id", slot["task_id"]).single().execute()
        name = task_r.data["name"] if task_r.data else "Skedule block"
        desc = task_r.data.get("description", "") if task_r.data else ""
        from api.calendar import get_calendar_service
        service = get_calendar_service(user_id, supabase)
        event = {
            "summary": name,
            "description": desc,
            "start": {"dateTime": slot["start_time"], "timeZone": "UTC"},
            "end": {"dateTime": slot["end_time"], "timeZone": "UTC"},
        }
        service.events().insert(calendarId="primary", body=event).execute()
    return {"ok": True, "added_to_calendar": body.add_to_calendar}


@router.post("/{suggestion_id}/reject")
def reject_slot(
    suggestion_id: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    r = (
        supabase.table("suggested_slots")
        .update({"status": "rejected"})
        .eq("id", suggestion_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not r.data or len(r.data) == 0:
        raise HTTPException(404, "Suggestion not found")
    return {"ok": True}
