from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.services.whatsapp_service import process_whatsapp_payload

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token and hub_challenge:
        return hub_challenge
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhook")
async def receive_webhook(request: Request):
    payload: dict[str, Any] = await request.json()

    if settings.environment != "development":
        raw_body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        # Optional: implement full signature verification for production hardening.
        if not signature:
            raise HTTPException(status_code=403, detail="Missing signature")
        _ = raw_body

    await process_whatsapp_payload(payload)
    return {"status": "ok"}


@router.get("/debug/session/{wa_id}")
async def debug_session(wa_id: str):
    from app.core.db import get_whatsapp_session_collection

    sessions = get_whatsapp_session_collection()
    item = await sessions.find_one({"wa_id": wa_id}, {"_id": 0})
    return item or {"wa_id": wa_id, "state": "none"}
