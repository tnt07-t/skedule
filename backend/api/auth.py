import logging
from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from api.deps import get_current_user_id, get_supabase, decode_access_token
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _user_id_from_token(access_token: str | None) -> str | None:
    if not access_token:
        return None
    try:
        payload = decode_access_token(access_token)
        return str(payload.get("sub"))
    except Exception:
        return None

SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"]
CALLBACK_URL = f"{settings.backend_url}/api/auth/google/callback"


def _flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [CALLBACK_URL],
            }
        },
        scopes=SCOPES,
        redirect_uri=CALLBACK_URL,
    )


@router.get("/google/connect")
def google_calendar_connect(
    access_token: str | None = Query(None, alias="access_token"),
):
    """Redirect to Google OAuth for Calendar. Token from Bearer header or ?access_token= (for link)."""
    uid = _user_id_from_token(access_token) if access_token else None
    if not uid:
        return RedirectResponse(url=f"{settings.app_url}?calendar_error=2")
    flow = _flow()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=uid,
    )
    return RedirectResponse(url=authorization_url)


@router.get("/google/callback")
async def google_calendar_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error or not code or not state:
        return RedirectResponse(url=f"{settings.app_url}?calendar_error=1")
    flow = _flow()
    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        user_id = state
        supabase = get_supabase()
        supabase.table("calendar_tokens").upsert(
            {
                "user_id": user_id,
                "refresh_token": creds.refresh_token,
                "access_token": creds.token,
                "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
            },
            on_conflict="user_id",
        ).execute()
        return RedirectResponse(url=f"{settings.app_url}?calendar_connected=1")
    except Exception:
        logger.exception("Google OAuth callback failed")
        return RedirectResponse(url=f"{settings.app_url}?calendar_error=1")
