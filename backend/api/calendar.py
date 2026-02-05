"""Google Calendar free-busy and add event."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import httpx

from api.deps import get_current_user_id, get_supabase
from api.time_utils import clamp_range
from config import settings

router = APIRouter()


def get_busy(user_id: str, supabase, start: str, end: str) -> list:
    """Return busy slots from primary calendar (for internal use)."""
    service = get_calendar_service(user_id, supabase)
    start_dt, end_dt = clamp_range(start, end, max_days=45)
    body = {
        "timeMin": start_dt.isoformat(),
        "timeMax": end_dt.isoformat(),
        "items": [{"id": "primary"}],
    }
    result = service.freebusy().query(body=body).execute()
    cal = result.get("calendars", {}).get("primary", {})
    return cal.get("busy", [])


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
            "token_expiry": datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600)),
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
    start_dt, end_dt = clamp_range(start, end)
    result = service.events().list(
        calendarId="primary",
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=2500,
    ).execute()
    items = result.get("items", [])
    events = []
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
