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
    # Try HS256 with shared secret first.
    if settings.supabase_jwt_secret:
        try:
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                audience="authenticated",
                algorithms=["HS256"],
            )
        except jwt.PyJWTError:
            pass
    # Fallback to JWKS (ES256/RS256) if project uses asymmetric signing.
    try:
        global _jwks_client
        if _jwks_client is None:
            jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
            _jwks_client = jwt.PyJWKClient(jwks_url)
        signing_key = _jwks_client.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            signing_key,
            audience="authenticated",
            algorithms=["ES256", "RS256"],
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token",
        )
    payload = decode_access_token(creds.credentials)
    return str(payload["sub"])
