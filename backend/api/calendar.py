"""Google Calendar free-busy and add event."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import httpx

from api.deps import get_current_user_id, get_supabase
from api.time_utils import clamp_range
from config import settings

router = APIRouter()


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
    items = _calendar_items(service, min_access_role="reader")
    ids: list[str] = []
    for cal in items:
        cid = cal.get("id")
        access_role = cal.get("accessRole")
        if not cid:
            continue
        if access_role == "freeBusyReader":
            continue
        if cid not in ids:
            ids.append(cid)
    if "primary" not in ids:
        ids.insert(0, "primary")
    return ids


def _calendar_ids_for_busy(service) -> list[str]:
    """Return calendar ids we can use for free/busy."""
    items = _calendar_items(service, min_access_role="freeBusyReader")
    ids: list[str] = []
    for cal in items:
        cid = cal.get("id")
        if cid and cid not in ids:
            ids.append(cid)
    if "primary" not in ids:
        ids.insert(0, "primary")
    return ids


def get_busy(user_id: str, supabase, start: str, end: str) -> list:
    """Return busy slots from calendars (for internal use)."""
    service = get_calendar_service(user_id, supabase)
    start_dt, end_dt = clamp_range(start, end, max_days=45)
    cal_ids = _calendar_ids_for_busy(service)
    body = {
        "timeMin": start_dt.isoformat(),
        "timeMax": end_dt.isoformat(),
        "items": [{"id": cid} for cid in cal_ids],
    }
    result = service.freebusy().query(body=body).execute()
    calendars = result.get("calendars", {})
    busy = []
    for cid in cal_ids:
        busy.extend(calendars.get(cid, {}).get("busy", []))
    return busy


def get_calendar_service(user_id: str, supabase):
    r = supabase.table("calendar_tokens").select("*").eq("user_id", user_id).single().execute()
    if not r.data:
        raise HTTPException(400, "Google Calendar not connected. Connect in Settings.")
    row = r.data
    token_expiry = row.get("token_expiry")
    if isinstance(token_expiry, str):
        token_expiry = datetime.fromisoformat(token_expiry.replace("Z", "+00:00"))
    creds = Credentials(
        token=row.get("access_token"),
        refresh_token=row.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=None,
        client_secret=None,
        scopes=["https://www.googleapis.com/auth/calendar"],
        expiry=token_expiry,
    )
    exp_naive = token_expiry.replace(tzinfo=None) if token_expiry and getattr(token_expiry, "tzinfo", None) else token_expiry
    need_refresh = bool(row.get("refresh_token") and (not exp_naive or datetime.utcnow() >= exp_naive))
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
    events = []
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
