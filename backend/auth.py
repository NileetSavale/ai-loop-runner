import os
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
# A project made since Supabase moved to signing keys signs tokens with a key pair (ES256 or RS256) and publishes the
# public keys here; an older one signs with SUPABASE_JWT_SECRET (HS256). Either, or both, may be set.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_jwks: jwt.PyJWKClient | None = None
# Local development only: requests without a token act as an ownerless local user
ALLOW_ANONYMOUS = os.getenv("ALLOW_ANONYMOUS", "").lower() == "true"
# ponytail: private beta gate. Loops run shell commands inside the backend pod, so a
# Supabase signup can't be enough on its own. Replace once runs are sandboxed.
ALLOWED_USER_IDS = {u.strip() for u in os.getenv("ALLOWED_USER_IDS", "").split(",") if u.strip()}

security = HTTPBearer(auto_error=False)


def _signing_keys() -> jwt.PyJWKClient:
    global _jwks
    if _jwks is None:
        # Fetched once and cached; a key Supabase rotates in is fetched when a token names it
        _jwks = jwt.PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json", cache_keys=True)
    return _jwks


def _decode(token: str) -> dict:
    algorithm = jwt.get_unverified_header(token).get("alg")
    if algorithm in ("ES256", "RS256"):
        if not SUPABASE_URL:
            raise jwt.InvalidTokenError("Auth is not configured: set SUPABASE_URL to check this token")
        try:
            key = _signing_keys().get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientError as e:
            raise jwt.InvalidTokenError(f"Couldn't get Supabase's signing key: {e}")
    elif algorithm == "HS256":
        if not SUPABASE_JWT_SECRET:
            raise jwt.InvalidTokenError("Auth is not configured: set SUPABASE_JWT_SECRET to check this token")
        key = SUPABASE_JWT_SECRET
    else:
        raise jwt.InvalidTokenError(f"Unsupported token algorithm {algorithm!r}")
    # The algorithm is pinned to the key's kind, so a token can't pick a weaker one
    return jwt.decode(token, key, algorithms=[algorithm], audience="authenticated", options={"require": ["sub"]})


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
