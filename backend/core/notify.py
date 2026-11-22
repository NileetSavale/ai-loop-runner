"""Push notifications to a user's devices when a session ends or waits for their approval.

Built but off until configured. Apple's push service (APNs) needs the paid Apple Developer Program: create an APNs
key there, then set PUSH_APNS_KEY_ID, PUSH_APNS_TEAM_ID, PUSH_APNS_KEY_PATH (the .p8 file) and PUSH_APNS_TOPIC (the
app's bundle id, com.looprunner.loopRunnerApp); PUSH_APNS_SANDBOX=true for development builds. Until then nothing is
sent, and the app's own notifications cover a session it is watching. Android (FCM) follows when the app has an
Android build.

Sending never blocks or breaks a session: it runs as its own task, and a failure is logged.
"""
import asyncio
import json
import logging
import os
import time

import jwt
from sqlmodel import select

from database import get_session as db_session
from models import DeviceToken, Session

log = logging.getLogger(__name__)

APNS_KEY_ID = os.getenv("PUSH_APNS_KEY_ID", "")
APNS_TEAM_ID = os.getenv("PUSH_APNS_TEAM_ID", "")
APNS_KEY_PATH = os.getenv("PUSH_APNS_KEY_PATH", "")
APNS_TOPIC = os.getenv("PUSH_APNS_TOPIC", "")
APNS_SANDBOX = os.getenv("PUSH_APNS_SANDBOX", "").lower() == "true"


def apns_configured() -> bool:
    return all((APNS_KEY_ID, APNS_TEAM_ID, APNS_KEY_PATH, APNS_TOPIC))


def message_for(event: dict, session_name: str) -> tuple[str, str] | None:
    """The notification a session event deserves, as (title, body), or None for an event that deserves none."""
    data = event.get("data") or {}
    if event.get("event") == "session_complete":
        return f"Session {data.get('status', 'ended')}", session_name
    if event.get("event") == "cascade" and data.get("step_kind") == "approve" and data.get("waiting"):
        return "Waiting for your approval", f"{session_name}: approve or reject the fix"
    return None


def _apns_token() -> str:
    """APNs provider token: an ES256 JWT signed with the .p8 key, valid for up to an hour."""
    with open(APNS_KEY_PATH) as f:
        key = f.read()
    return jwt.encode({"iss": APNS_TEAM_ID, "iat": int(time.time())}, key, algorithm="ES256",
                      headers={"kid": APNS_KEY_ID})


async def _send_apns(device_token: str, title: str, body: str, session_id: str):
    import httpx  # HTTP/2 needs the h2 package (requirements.txt)
    host = "api.sandbox.push.apple.com" if APNS_SANDBOX else "api.push.apple.com"
    async with httpx.AsyncClient(http2=True, timeout=10) as client:
        response = await client.post(
            f"https://{host}/3/device/{device_token}",
            headers={"authorization": f"bearer {_apns_token()}", "apns-topic": APNS_TOPIC, "apns-push-type": "alert"},
            content=json.dumps({"aps": {"alert": {"title": title, "body": body}, "sound": "default"},
                                "session_id": session_id}),
        )
    if response.status_code != 200:
        log.warning("APNs refused a notification: %s %s", response.status_code, response.text)


async def _deliver(session_id: str, title: str, body: str):
    with db_session() as db:
        session = db.get(Session, session_id)
        if session is None:
            return
        devices = db.exec(select(DeviceToken).where(DeviceToken.user_id == session.user_id)).all()
    for device in devices:
        try:
            if device.platform == "ios" and apns_configured():
                await _send_apns(device.token, title, body, session_id)
        except Exception:
            log.exception("Push to a %s device failed", device.platform)


def notify(session_id: str, event: dict):
    """Called for every event a session broadcasts; sends the ones that deserve a notification, in the background."""
    if not apns_configured():
        return  # nothing to send with: the app's own notifications cover a session it watches
    with db_session() as db:
        session = db.get(Session, session_id)
    message = message_for(event, session.name if session else "A session") if session else None
    if message:
        asyncio.get_running_loop().create_task(_deliver(session_id, *message))
