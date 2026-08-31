import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from models import ApiKey
from database import get_session as db_session
from auth import get_current_user, user_id
from vault import encrypt, decrypt
from providers.base import SUPPORTED_MODELS

router = APIRouter(prefix="/keys", tags=["keys"])


class KeyCreate(BaseModel):
    provider: str   # anthropic | openai | google | mistral
    api_key: str
    label: str = ""


@router.get("/models")
def list_models():
    """Public — no auth needed. Returns all supported models grouped by provider."""
    return SUPPORTED_MODELS


@router.get("")
def list_keys(user: dict = Depends(get_current_user)):
    with db_session() as db:
        keys = db.exec(select(ApiKey).where(ApiKey.user_id == user_id(user))).all()
    return [
        {"id": k.id, "provider": k.provider, "label": k.label, "created_at": k.created_at}
        for k in keys
    ]  # never return the encrypted key


@router.post("")
def add_key(body: KeyCreate, user: dict = Depends(get_current_user)):
    if body.provider not in SUPPORTED_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")

    uid = user_id(user)
    with db_session() as db:
        # one key per provider per user — replace if exists
        existing = db.exec(
            select(ApiKey).where(ApiKey.user_id == uid, ApiKey.provider == body.provider)
        ).first()
        if existing:
            existing.encrypted_key = encrypt(body.api_key)
            existing.label = body.label or body.provider
            db.add(existing)
            db.commit()
            return {"id": existing.id, "provider": existing.provider}

        key = ApiKey(
            id=str(uuid.uuid4()),
            user_id=uid,
            provider=body.provider,
            encrypted_key=encrypt(body.api_key),
            label=body.label or body.provider,
        )
        db.add(key)
        db.commit()
    return {"id": key.id, "provider": key.provider}


@router.delete("/{key_id}")
def delete_key(key_id: str, user: dict = Depends(get_current_user)):
    with db_session() as db:
        key = db.get(ApiKey, key_id)
        if not key or key.user_id != user_id(user):
            raise HTTPException(status_code=404)
        db.delete(key)
        db.commit()
    return {"deleted": key_id}


def get_user_api_key(uid: str, model: str) -> str | None:
    """Called by the loop — returns decrypted BYOK key or None (→ platform key)."""
    from providers.router import _provider_for
    provider = _provider_for(model)
    with db_session() as db:
        key = db.exec(
            select(ApiKey).where(ApiKey.user_id == uid, ApiKey.provider == provider)
        ).first()
    return decrypt(key.encrypted_key) if key else None
