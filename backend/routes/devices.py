"""Devices that want push notifications (core/notify.py)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from auth import get_optional_user, user_id
from database import get_session as db_session
from models import DeviceToken

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceCreate(BaseModel):
    platform: str = Field(pattern="^(ios|android|macos)$")
    token: str = Field(min_length=8, max_length=512)


@router.post("")
def register_device(body: DeviceCreate, user: dict | None = Depends(get_optional_user)):
    """Idempotent: the same token registers once."""
    uid = user_id(user) if user else None
    with db_session() as db:
        existing = db.exec(select(DeviceToken).where(DeviceToken.token == body.token)).first()
        if existing:
            existing.user_id, existing.platform = uid, body.platform
            db.add(existing)
            db.commit()
            return {"id": existing.id}
        device = DeviceToken(id=str(uuid.uuid4()), user_id=uid, platform=body.platform, token=body.token)
        db.add(device)
        db.commit()
        return {"id": device.id}


@router.delete("/{device_id}")
def remove_device(device_id: str, user: dict | None = Depends(get_optional_user)):
    uid = user_id(user) if user else None
    with db_session() as db:
        device = db.get(DeviceToken, device_id)
        if device is None or device.user_id != uid:
            raise HTTPException(status_code=404, detail="Device not found")
        db.delete(device)
        db.commit()
    return {"deleted": device_id}
