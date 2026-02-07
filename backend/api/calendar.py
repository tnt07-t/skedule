"""Google Calendar free-busy and add event."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import httpx

from api.deps import get_current_user_id, get_supabase
from api.time_utils import clamp_range, parse_iso
from config import settings

router = APIRouter()

CACHE_TTL_SECONDS = 1800


def _calendar_items(service, min_access_role: str) -> list[dict]:
    items: list[dict] = []
    page_token = None
    while True:
        resp = service.calendarList().list(
            minAccessRole=min_access_role,
            showHidden=True,
            pageToken=page_token,
        ).execute()
        items.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def _calendar_ids_for_events(service) -> list[str]:
    """Return calendar ids we can list events from."""
    return ["primary"]


def _calendar_ids_for_busy(service) -> list[str]:
    """Return calendar ids we can use for free/busy."""
    return ["primary"]


def _fetch_busy(service, start_dt: datetime, end_dt: datetime, cal_ids: list[str]) -> list[dict]:
    body = {
        "timeMin": start_dt.isoformat(),
        "timeMax": end_dt.isoformat(),
        "items": [{"id": cid} for cid in cal_ids],
    }
    result = service.freebusy().query(body=body).execute()
    calendars = result.get("calendars", {})
    busy: list[dict] = []
    for cid in cal_ids:
        busy.extend(calendars.get(cid, {}).get("busy", []))
    return busy


def _list_events(service, start_dt: datetime, end_dt: datetime, cal_ids: list[str]) -> list[dict]:
    events: list[dict] = []
    for cid in cal_ids:
        try:
            result = service.events().list(
                calendarId=cid,
                timeMin=start_dt.isoformat(),
                timeMax=end_dt.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
            ).execute()
        except Exception:
            continue
        items = result.get("items", [])
        for e in items:
            start_obj = e.get("start", {})
            end_obj = e.get("end", {})
            if "dateTime" in start_obj:
                start_val = start_obj.get("dateTime")
                end_val = end_obj.get("dateTime")
                all_day = False
            else:
                start_val = start_obj.get("date")
                end_val = end_obj.get("date")
                all_day = True
            events.append(
                {
                    "id": e.get("id"),
                    "summary": e.get("summary", "Busy"),
                    "start": start_val,
                    "end": end_val,
                    "all_day": all_day,
                }
            )
    return events


def _free_from_busy(busy: list[dict], start_dt: datetime, end_dt: datetime) -> list[dict]:
    intervals = []
    for b in busy:
        try:
            b_start = parse_iso(b["start"])
            b_end = parse_iso(b["end"])
        except Exception:
            continue
        if b_end <= start_dt or b_start >= end_dt:
            continue
        if b_start < start_dt:
            b_start = start_dt
        if b_end > end_dt:
            b_end = end_dt
        if b_end > b_start:
            intervals.append((b_start, b_end))
    if not intervals:
        return [{"start": start_dt.isoformat(), "end": end_dt.isoformat()}]
    intervals.sort(key=lambda x: x[0])
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        last_s, last_e = merged[-1]
        if s <= last_e:
            if e > last_e:
                merged[-1] = (last_s, e)
        else:
            merged.append((s, e))
    free = []
    cursor = start_dt
    for s, e in merged:
        if s > cursor:
            free.append({"start": cursor.isoformat(), "end": s.isoformat()})
        if e > cursor:
            cursor = e
    if cursor < end_dt:
        free.append({"start": cursor.isoformat(), "end": end_dt.isoformat()})
    return free


def get_busy(user_id: str, supabase, start: str, end: str) -> list:
    """Return busy slots from calendars (for internal use)."""
    service = get_calendar_service(user_id, supabase)
    start_dt, end_dt = clamp_range(start, end, max_days=45)
    cal_ids = _calendar_ids_for_busy(service)
    return _fetch_busy(service, start_dt, end_dt, cal_ids)


def get_calendar_service(user_id: str, supabase):
    r = supabase.table("calendar_tokens").select("*").eq("user_id", user_id).single().execute()
    if not r.data:
        raise HTTPException(400, "Google Calendar not connected. Connect in Settings.")
    row = r.data
    if not row.get("access_token") or not row.get("refresh_token"):
        raise HTTPException(400, "Google Calendar token missing; reconnect your calendar.")
    token_expiry = row.get("token_expiry")
    if isinstance(token_expiry, str):
        raw = token_expiry
        try:
            token_expiry = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            try:
                token_expiry = datetime.fromisoformat(raw.split(".")[0] + "+00:00")
            except Exception:
                token_expiry = None
    if token_expiry and token_expiry.tzinfo is not None:
        # google-auth compares against a naive utcnow(); keep expiry naive UTC too
        token_expiry = token_expiry.astimezone(timezone.utc).replace(tzinfo=None)
    creds = Credentials(
        token=row.get("access_token"),
        refresh_token=row.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=["https://www.googleapis.com/auth/calendar"],
        expiry=token_expiry,
    )
    now_naive = datetime.utcnow()
    need_refresh = bool(row.get("refresh_token") and (not token_expiry or now_naive >= token_expiry))
    if need_refresh:
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": creds.refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = resp.json()
        creds = Credentials(
            token=data["access_token"],
            refresh_token=creds.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
        supabase.table("calendar_tokens").update({
            "access_token": data["access_token"],
            "token_expiry": (datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))).isoformat(),
        }).eq("user_id", user_id).execute()
    return build("calendar", "v3", credentials=creds)


@router.get("/free-busy")
def free_busy_route(
    start: str,
    end: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Return free-busy from primary calendar."""
    return {"busy": get_busy(user_id, supabase, start, end)}


@router.get("/events")
def list_events(
    start: str,
    end: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Return events from primary calendar."""
    service = get_calendar_service(user_id, supabase)
    start_dt, end_dt = clamp_range(start, end, max_days=45)
    cal_ids = _calendar_ids_for_events(service)
    return _list_events(service, start_dt, end_dt, cal_ids)


@router.get("/week")
def week_summary(
    start: str,
    end: str,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Return events, busy, and free blocks for a week."""
<<<<<<< HEAD
    service = get_calendar_service(user_id, supabase)
    start_dt, end_dt = clamp_range(start, end, max_days=7)
=======
    start_dt, end_dt = clamp_range(start, end, max_days=7)
    cache_start = start_dt.isoformat()
    cache_end = end_dt.isoformat()
    now = datetime.now(timezone.utc)
    try:
        cached = (
            supabase.table("calendar_week_cache")
            .select("*")
            .eq("user_id", user_id)
            .eq("week_start", cache_start)
            .eq("week_end", cache_end)
            .order("fetched_at", desc=True)
            .limit(1)
            .execute()
        )
        if cached.data:
            row = cached.data[0]
            fetched_at = row.get("fetched_at")
            if isinstance(fetched_at, str):
                fetched_at = parse_iso(fetched_at)
            if fetched_at and fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            if fetched_at and (now - fetched_at).total_seconds() <= CACHE_TTL_SECONDS:
                return {
                    "events": row.get("events", []),
                    "busy": row.get("busy", []),
                    "free": row.get("free", []),
                }
    except Exception:
        pass

    service = get_calendar_service(user_id, supabase)
>>>>>>> tran-cache
    cal_ids = _calendar_ids_for_events(service)
    events = _list_events(service, start_dt, end_dt, cal_ids)
    busy = _fetch_busy(service, start_dt, end_dt, cal_ids)
    free = _free_from_busy(busy, start_dt, end_dt)
<<<<<<< HEAD
    return {"events": events, "busy": busy, "free": free}
=======
    payload = {"events": events, "busy": busy, "free": free}
    try:
        supabase.table("calendar_week_cache").upsert(
            {
                "user_id": user_id,
                "week_start": cache_start,
                "week_end": cache_end,
                "events": events,
                "busy": busy,
                "free": free,
                "fetched_at": now.isoformat(),
            }
        ).execute()
    except Exception:
        pass
    return payload
>>>>>>> tran-cache


@router.post("/events")
def add_event(
    summary: str,
    start: str,
    end: str,
    description: str = "",
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Add event to primary calendar."""
    service = get_calendar_service(user_id, supabase)
    event = {
        "summary": summary,
        "description": description or "",
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return created
