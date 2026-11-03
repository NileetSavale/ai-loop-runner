import os
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
# Local development only: requests without a token act as an ownerless local user
ALLOW_ANONYMOUS = os.getenv("ALLOW_ANONYMOUS", "").lower() == "true"
# ponytail: private beta gate. Loops run shell commands inside the backend pod, so a
# Supabase signup can't be enough on its own. Replace once runs are sandboxed.
ALLOWED_USER_IDS = {u.strip() for u in os.getenv("ALLOWED_USER_IDS", "").split(",") if u.strip()}

security = HTTPBearer(auto_error=False)


def _decode(token: str) -> dict:
    if not SUPABASE_JWT_SECRET:
        raise jwt.InvalidTokenError("Auth is not configured")
    return jwt.decode(
        token,
        SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience="authenticated",
        options={"require": ["sub"]},
    )


def resolve_user(token: str | None) -> dict | None:
    """Return the verified user. None only means anonymous local use (ALLOW_ANONYMOUS)."""
    if not token:
        if ALLOW_ANONYMOUS:
            return None
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user = _decode(token)
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
    if not ALLOW_ANONYMOUS and user["sub"] not in ALLOWED_USER_IDS:
        raise HTTPException(status_code=403, detail="Account not enabled for this beta")
    return user


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return resolve_user(creds.credentials)


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    return resolve_user(creds.credentials if creds else None)


def user_id(user: dict) -> str:
    return user["sub"]
