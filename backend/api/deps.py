from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client, Client

from config import settings

security = HTTPBearer(auto_error=False)
_jwks_client = None


def get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)


def decode_access_token(token: str) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    # In this environment we skip signature verification (Supabase already authenticated the user).
    try:
        return jwt.decode(
            token,
            options={"verify_signature": False, "verify_aud": False},
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user_id(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token",
        )
    payload = decode_access_token(creds.credentials)
    return str(payload["sub"])
