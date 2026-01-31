import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client, Client

from config import settings

security = HTTPBearer(auto_error=False)


def get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)


def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token",
        )
    try:
        payload = jwt.decode(
            creds.credentials,
            settings.supabase_jwt_secret,
            audience="authenticated",
            algorithms=["HS256"],
        )
        return str(payload["sub"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
