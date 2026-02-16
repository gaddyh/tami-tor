# apps/bot.py
from __future__ import annotations

import os
import hmac
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.responses import Response, JSONResponse, PlainTextResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from temporalio.client import Client
from adapters.temporal.client_cloud import temporal_client_from_env

from apps.webhook_ingest import persist_inbound
from runtime.events import emit_event

from models.input import InboundEvent
from workflows.main import update_provider_workflow_with_start, update_client_workflow_with_start, TASK_QUEUE, resolve_user_route_async
from db.session_async import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession
from adapters.cloud_api import CloudAPIAdapter


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "...")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
templates = Jinja2Templates(directory="apps/templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Temporal client
    app.state.temporal_client = await temporal_client_from_env()

    # Initialize adapter (singleton per process)
    app.state.adapter = CloudAPIAdapter(WHATSAPP_PHONE_NUMBER_ID)

    yield


app = FastAPI(title="tami", lifespan=lifespan)


def _peek_textish(m: dict) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    msg_type = m.get("type")
    text = None
    caption = None
    interactive_type = None
    button_text = None

    if msg_type == "text":
        text = (m.get("text") or {}).get("body")

    elif msg_type in ("image", "video", "audio", "document"):
        caption = (m.get(msg_type) or {}).get("caption")

    elif msg_type == "interactive":
        interactive = m.get("interactive") or {}
        interactive_type = interactive.get("type")
        if interactive_type == "button_reply":
            button_text = ((interactive.get("button_reply") or {}).get("title"))
        elif interactive_type == "list_reply":
            button_text = ((interactive.get("list_reply") or {}).get("title"))

    elif msg_type == "button":
        btn = m.get("button") or {}
        button_text = btn.get("text")

    return text, caption, interactive_type, button_text


def _to_inbound_event(mid: str, client_id: str, m: dict) -> InboundEvent:
    msg_type = (m.get("type") or "unknown").lower()

    if msg_type == "audio":
        audio = m.get("audio") or {}
        audio_id = (audio.get("id") or "").strip()
        return InboundEvent(event_id=mid, client_id=client_id, kind="audio", audio_id=audio_id)

    if msg_type == "text":
        text = ((m.get("text") or {}).get("body") or "").strip()
        return InboundEvent(event_id=mid, client_id=client_id, kind="text", text=text)

    if msg_type == "interactive":
        interactive = m.get("interactive") or {}
        itype = (interactive.get("type") or "").lower()

        if itype == "list_reply":
            list_id = ((interactive.get("list_reply") or {}).get("id") or "").strip()
            return InboundEvent(event_id=mid, client_id=client_id, kind="list", list_id=list_id)

        if itype == "button_reply":
            button_id = ((interactive.get("button_reply") or {}).get("id") or "").strip()
            return InboundEvent(event_id=mid, client_id=client_id, kind="button", button_id=button_id)

    if msg_type == "button":
        btn = m.get("button") or {}
        button_id = (btn.get("payload") or btn.get("text") or "").strip()
        return InboundEvent(event_id=mid, client_id=client_id, kind="button", button_id=button_id)

    return InboundEvent(event_id=mid, client_id=client_id, kind="unknown")


@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("Webhook verification succeeded.")
        return hub_challenge or ""
    logger.warning("Webhook verification failed.")
    raise HTTPException(status_code=403, detail="Verification failed")

from fastapi import Depends

@app.post("/webhook")
async def webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=None),
):
    body_bytes = await request.body()

    # Turn on signature verification when ready
    if APP_SECRET:
        expected_signature = "sha256=" + hmac.new(
            APP_SECRET.encode(), body_bytes, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, x_hub_signature_256 or ""):
            logger.warning("Signature verification failed.")
            raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        raw_data = await request.json()
    except Exception:
        logger.exception("Failed to parse JSON body")
        return Response(status_code=200)

    saw_messages = False
    new_signals = 0
    duplicates = 0

    assert temporal_client is not None, "Temporal client not initialized"

    try:
        for entry in (raw_data.get("entry") or []):
            for change in (entry.get("changes") or []):
                value = change.get("value") or {}
                metadata = value.get("metadata") or {}
                phone_number_id = (metadata.get("phone_number_id") or "").strip()

                messages = value.get("messages") or []
                if not messages:
                    continue

                for m in messages:
                    saw_messages = True
                    mid = (m.get("id") or "").strip()
                    if not mid:
                        continue

                    client_id = (m.get("from") or "").strip() or "unknown"

                    # logging peek
                    try:
                        msg_type = m.get("type")
                        keys = list(m.keys())
                        text, caption, interactive_type, button_text = _peek_textish(m)
                        logger.info(
                            "INBOUND mid=%s from=%s type=%s keys=%s text=%s caption=%s interactive=%s button=%s",
                            mid, client_id, msg_type, keys,
                            (text[:120] if text else None),
                            (caption[:120] if caption else None),
                            interactive_type, button_text,
                        )
                    except Exception:
                        logger.exception("Logging failed")

                    inserted, inbound_db_id, _from_value = persist_inbound(
                        message_id=mid,
                        phone_number_id=phone_number_id,
                        raw_message=m,
                    )

                    if not inserted:
                        duplicates += 1
                        continue

                    ev = _to_inbound_event(mid, client_id, m)

                    db: AsyncSession = await get_async_db()
                    route_result = await resolve_user_route_async(db, client_id)
                  
                    if route_result.is_provider:
                        await update_provider_workflow_with_start(
                            business_id=route_result.business_id,
                            client_id=client_id,
                            ev=ev,
                            temporal_client=temporal_client,
                        )
                    else:
                        await update_client_workflow_with_start(
                            business_id=route_result.business_id,
                            client_id=client_id,
                            ev=ev,
                            temporal_client=temporal_client,
                        )

                    new_signals += 1
                    wf_id = f"booking:{route_result.business_id}:{client_id}"

                    emit_event(
                        event="TEMPORAL_SIGNAL_SENT",
                        meta={
                            "workflow_id": wf_id,
                            "task_queue": TASK_QUEUE,
                            "event_id": mid,
                            "inbound_db_id": str(inbound_db_id) if inbound_db_id else None,
                            "business_id": route_result.business_id,
                            "client_id": client_id,
                            "phone_number_id": phone_number_id,
                        },
                    )

    except Exception:
        logger.exception("Failed to ingest messages")

    if new_signals > 0:
        logger.info("Signaled %d new messages (duplicates=%d)", new_signals, duplicates)
        return Response(status_code=200)

    if saw_messages and new_signals == 0:
        return JSONResponse({"status": "duplicate", "duplicates": duplicates}, status_code=200)

    return Response(status_code=200)
