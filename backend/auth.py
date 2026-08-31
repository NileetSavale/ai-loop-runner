import os
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

security = HTTPBearer(auto_error=False)


def _decode(token: str) -> dict:
    return jwt.decode(
        token,
        SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience="authenticated",
    )


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return _decode(creds.credentials)
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    if not creds:
        return None
    try:
        return _decode(creds.credentials)
    except jwt.InvalidTokenError:
        return None


def user_id(user: dict) -> str:
    return user["sub"]
