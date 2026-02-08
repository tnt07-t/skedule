"""Suggest time blocks from free-busy and task prefs; approve/reject."""
from typing import Optional
from datetime import datetime, timedelta, timezone
import math
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
# Cap pending suggestions per user to keep UI manageable
MAX_SUGGESTIONS = 15


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


def _minutes_between(start: str, end: str) -> int:
    try:
        s = parse_iso(start)
        e = parse_iso(end)
    except Exception:
        return 0
    delta = e - s
    return max(0, int(round(delta.total_seconds() / 60.0)))


def _approved_minutes_for_task(supabase, task_id: str, user_id: str) -> int:
    res = (
        supabase.table("suggested_slots")
        .select("start_time,end_time")
        .eq("task_id", task_id)
        .eq("user_id", user_id)
        .eq("status", "approved")
        .execute()
    )
    total = 0
    for row in res.data or []:
        total += _minutes_between(row.get("start_time"), row.get("end_time"))
    return total


def _task_complete(task: dict, approved_minutes: int) -> bool:
    estimated = _coerce_minutes(task.get("estimated_minutes"))
    if estimated is None:
        return False
    return approved_minutes >= estimated


def _desired_limit_for_task(task: dict, approved_minutes: int, requested_limit: int) -> int:
    base = max(3, min(requested_limit, 20))
    duration_min = FOCUS_MINUTES.get(task["focus_level"], 50)
    estimated = _coerce_minutes(task.get("estimated_minutes"))
    if estimated is None:
        return base
    remaining = max(0, estimated - approved_minutes)
    if remaining <= 0:
        return base
    needed = int(math.ceil(remaining / max(1, duration_min)))
    return max(base, min(20, needed))


def _score_slot(slot_start: datetime, range_start: datetime, pref_center_minutes: int) -> float:
    minutes_from_start = (slot_start - range_start).total_seconds() / 60.0
    time_of_day = slot_start.hour * 60 + slot_start.minute
    pref_distance = abs(time_of_day - pref_center_minutes)
    # Prefer earlier times to reduce procrastination, then closer to preference center.
    return (-minutes_from_start) - (0.1 * pref_distance)


def _generate_suggestions_for_task(
    task: dict,
    user_id: str,
    supabase,
    start_dt: datetime,
    end_dt: datetime,
    limit: int,
):
    duration_min = FOCUS_MINUTES.get(task["focus_level"], 50)
    pref = task.get("time_preference", "midday")
    h_start, h_end = PREF_HOURS.get(pref, (12, 17))
    pref_center_minutes = int(((h_start + h_end) / 2) * 60)

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

    # Clear any pending suggestions for this task to avoid duplicates/clutter
    supabase.table("suggested_slots").delete().eq("task_id", task["id"]).eq("user_id", user_id).eq("status", "pending").execute()

    # Treat existing suggestions (pending/approved) as busy so we don't stack on top
    existing_busy = []
    for status in ("pending", "approved"):
        res = (
            supabase.table("suggested_slots")
            .select("start_time,end_time")
            .eq("user_id", user_id)
            .eq("status", status)
            .gte("start_time", start_dt.isoformat())
            .lte("end_time", end_dt.isoformat())
            .execute()
        )
        existing_busy.extend(
            {"start": row["start_time"], "end": row["end_time"]} for row in (res.data or [])
        )

    ranked_slots = []
    seen = set()  # dedupe by exact start/end within this run
    for cs, ce in candidates:
        busy = get_busy(user_id, supabase, cs.isoformat(), ce.isoformat()) + existing_busy
        for s_start, s_end in slots_from_busy(busy, cs, ce, duration_min):
            key = f"{s_start}|{s_end}"
            if key in seen:
                continue
            seen.add(key)
            score = _score_slot(parse_iso(s_start), start_dt, pref_center_minutes)
            ranked_slots.append((score, s_start, s_end))

    ranked_slots.sort(key=lambda row: (row[0], row[1]), reverse=True)
    suggestions_list = []
    for _, s_start, s_end in ranked_slots[:limit]:
        r = (
            supabase.table("suggested_slots")
            .insert(
                {
                    "task_id": task["id"],
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


def _suggestions_remaining(user_id: str, supabase, statuses: tuple = ("pending",)) -> int:
    """Return how many more suggestions we can create, counting only specified statuses (default pending)."""
    r = (
        supabase.table("suggested_slots")
        .select("id", count="exact", head=True)
        .eq("user_id", user_id)
        .in_("status", list(statuses))
        .execute()
    )
    # postgrest returns count in r.count when head=True
    current = r.count or 0
    return max(0, MAX_SUGGESTIONS - current)


@router.post("/suggest/{task_id}")
def suggest_slots(
    task_id: str,
    start: str,
    end: str,
    limit: int = 5,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Compute suggested slots for task and save; return suggestions."""
    limit = max(3, min(limit, 20))  # clamp between 3 and 20 to avoid overload
    remaining = _suggestions_remaining(user_id, supabase, statuses=("pending",))
    if remaining <= 0:
        raise HTTPException(400, f"Maximum pending suggestions reached ({MAX_SUGGESTIONS}). Reject or approve some before adding more.")
    limit = min(limit, remaining)
    # Get task
    tr = supabase.table("tasks").select("*").eq("id", task_id).eq("user_id", user_id).single().execute()
    if not tr.data:
        raise HTTPException(404, "Task not found")
    task = tr.data

    start_dt, end_dt = clamp_range(start, end)
    approved_minutes = _approved_minutes_for_task(supabase, task_id, user_id)
    limit = _desired_limit_for_task(task, approved_minutes, limit)
    if _task_complete(task, approved_minutes):
        supabase.table("suggested_slots").delete().eq("task_id", task_id).eq("user_id", user_id).eq("status", "pending").execute()
        return []

    return _generate_suggestions_for_task(task, user_id, supabase, start_dt, end_dt, limit)


@router.get("")
def list_suggestions(
    task_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    q = supabase.table("suggested_slots").select("*").eq("user_id", user_id)
    if task_id:
        q = q.eq("task_id", task_id)
    r = q.order("start_time").execute()
    # Enrich with task name for frontend display
    if not r.data:
        return []
    task_ids = list({row["task_id"] for row in r.data})
    task_names = {}
    if task_ids:
        names_r = (
            supabase.table("tasks")
            .select("id,name")
            .in_("id", task_ids)
            .execute()
        )
        for row in names_r.data or []:
            task_names[row["id"]] = row.get("name", "")
    for row in r.data:
        row["task_name"] = task_names.get(row["task_id"], "")
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
    task = {}
    try:
        task_r = (
            supabase.table("tasks")
            .select("estimated_minutes")
            .eq("id", slot["task_id"])
            .eq("user_id", user_id)
            .execute()
        )
        if task_r.data:
            task = task_r.data[0]
    except Exception as e:
        if "estimated_minutes" in str(e):
            raise HTTPException(500, "DB migration missing: run 004_task_estimated_minutes.sql") from e
        task = {}
    approved_minutes = _approved_minutes_for_task(supabase, slot["task_id"], user_id)
    task_complete = _task_complete(task, approved_minutes)
    if task_complete:
        supabase.table("suggested_slots").delete().eq("task_id", slot["task_id"]).eq("user_id", user_id).eq("status", "pending").execute()
    return {
        "ok": True,
        "added_to_calendar": body.add_to_calendar,
        "task_complete": task_complete,
        "approved_minutes": approved_minutes,
        "estimated_minutes": _coerce_minutes(task.get("estimated_minutes")),
    }


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


@router.post("/reject-all")
def reject_all(
    task_id: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 5,
    resuggest: bool = False,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    q = supabase.table("suggested_slots").update({"status": "rejected"}).eq("user_id", user_id).eq("status", "pending")
    if task_id:
        q = q.eq("task_id", task_id)
    r = q.execute()
    resuggested = 0
    if resuggest:
        remaining = _suggestions_remaining(user_id, supabase, statuses=("pending",))
        if remaining <= 0:
            return {"ok": True, "rejected": len(r.data or []), "resuggested": 0, "message": f"Maximum pending suggestions reached ({MAX_SUGGESTIONS}). Reject or approve some before adding more."}
        if start and end:
            start_dt, end_dt = clamp_range(start, end)
        else:
            now = datetime.now(timezone.utc)
            start_dt = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
            end_dt = start_dt + timedelta(days=7)
        limit = max(3, min(limit, 20))
        if task_id:
            task_r = (
                supabase.table("tasks")
                .select("*")
                .eq("id", task_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            tasks = [task_r.data] if task_r.data else []
        else:
            tasks_r = supabase.table("tasks").select("*").eq("user_id", user_id).execute()
            tasks = tasks_r.data or []
        for task in tasks:
            approved_minutes = _approved_minutes_for_task(supabase, task["id"], user_id)
            task_limit = _desired_limit_for_task(task, approved_minutes, limit)
            if _task_complete(task, approved_minutes):
                continue
            if remaining <= 0:
                break
            take = min(task_limit, remaining)
            created = _generate_suggestions_for_task(task, user_id, supabase, start_dt, end_dt, take)
            resuggested += len(created)
            remaining -= len(created)
    return {"ok": True, "rejected": len(r.data or []), "resuggested": resuggested}
