# apps/bot.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import select

from db.session import SessionLocal
from models.session import Session
from runtime.redis_client import enqueue_outbox

import os
import json
from fastapi import Header, HTTPException
from sqlalchemy import func
from runtime.redis_client import redis_client, QUEUE_OUTBOX
import hmac
import hashlib
import logging
import time

from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse, HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from adapters.google.oauth import google_router

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
from fastapi import FastAPI
from contextlib import asynccontextmanager, suppress
from typing import Optional

app = FastAPI(title="tami")
app.include_router(google_router) #auth connect
templates = Jinja2Templates(directory="apps/templates")


class HelloIn(BaseModel):
    business_id: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)


class HelloOut(BaseModel):
    session_id: str
    outbox_id: str
    status: str


@app.get("/success", response_class=HTMLResponse)
async def google_connect_success(request: Request):
    return templates.TemplateResponse("google_success.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})

@app.get("/connect", response_class=HTMLResponse)
async def google_connect_page(request: Request):
        return templates.TemplateResponse("google_connect.html", {"request": request})

@app.get("/health")
def health():
    return {"ok": True}
from runtime.events import emit_event
from runtime.redis_client import QUEUE_OUTBOX

@app.post("/hello", response_model=HelloOut)
def hello(inp: HelloIn) -> HelloOut:
    with SessionLocal() as db:
        existing = db.execute(
            select(Session)
            .where(Session.business_id == inp.business_id)
            .where(Session.client_id == inp.client_id)
            .where(Session.status == "active")
            .limit(1)
        ).scalar_one_or_none()

        if existing:
            session = existing
            session.updated_at = datetime.now(timezone.utc)
        else:
            session = Session(
                business_id=inp.business_id,
                client_id=inp.client_id,
                status="active",
                state_json={},
            )
            db.add(session)
            db.flush()

        outbox = Outbox(
            type="HELLO",
            business_id=inp.business_id,
            client_id=inp.client_id,
            session_id=session.session_id,
            payload_json={"text": "Hello from outbox"},
            status="pending",
        )
        db.add(outbox)
        db.commit()  # outbox is durable now

        # ✅ log: durable DB row exists
        emit_event(
            event="OUTBOX_COMMITTED",
            outbox_id=str(outbox.outbox_id),
            type=outbox.type,
            business_id=outbox.business_id,
            client_id=outbox.client_id,
            session_id=str(outbox.session_id),
            meta={"where": "web"},
        )

        # ✅ enqueue to Redis
        enqueue_outbox(str(outbox.outbox_id))

        # ✅ log: redis push happened
        emit_event(
            event="OUTBOX_ENQUEUED",
            outbox_id=str(outbox.outbox_id),
            type=outbox.type,
            business_id=outbox.business_id,
            client_id=outbox.client_id,
            session_id=str(outbox.session_id),
            meta={"queue": QUEUE_OUTBOX},
        )

        return HelloOut(
            session_id=str(session.session_id),
            outbox_id=str(outbox.outbox_id),
            status="enqueued",
        )
import json
import os

from fastapi import Header, HTTPException
from sqlalchemy import select, func

from db.session import SessionLocal
from runtime.redis_client import redis_client, QUEUE_WORK  # make sure QUEUE_WORK exists
from apps.config import WORK_STREAM_KEY  # or whatever you named your stream key

from models.work_item import WorkItem
from models.inbound_message import InboundMessage

from dotenv import load_dotenv
load_dotenv(".venv/.env")

from apps.debug import debug_ui

@app.get("/debug/ui", response_class=HTMLResponse)
def debug_ui_endpoint(token: str, count: int = 20):
    return debug_ui(token, count)

# apps/bot.py (or wherever your FastAPI app is)

import hmac
import hashlib
import json
import time
from typing import Optional

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import Response, JSONResponse

from apps.webhook_ingest import persist_inbound_and_enqueue

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "...")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")

def _peek_textish(m: dict) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Keep your existing helper if you have it.
    This is only for logging; not required for correctness.
    """
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

@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    print("hub_mode", hub_mode)
    print("hub_verify_token", hub_verify_token)
    print("hub_challenge", hub_challenge)
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("Webhook verification succeeded.")
        return hub_challenge or ""
    logger.warning("Webhook verification failed.")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=None)
):
    body_bytes = await request.body()

    # Verify Meta signature if app secret is set
    if APP_SECRET and False:
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
    new_jobs = 0
    duplicates = 0

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

                    # Optional: log peek fields
                    try:
                        msg_type = m.get("type")
                        keys = list(m.keys())
                        text, caption, interactive_type, button_text = _peek_textish(m)

                        logger.info(
                            "INBOUND mid=%s from=%s type=%s keys=%s text=%s caption=%s interactive=%s button=%s",
                            mid, m.get("from"), msg_type, keys,
                            (text[:120] if text else None),
                            (caption[:120] if caption else None),
                            interactive_type, button_text
                        )
                    except Exception:
                        logger.exception("Logging failed")

                    # Persist + enqueue inbound (InboundMessage is the durable work item)
                    inserted = persist_inbound_and_enqueue(
                        message_id=mid,
                        phone_number_id=phone_number_id,
                        raw_message=m,  # single message object
                    )

                    if inserted:
                        new_jobs += 1
                    else:
                        duplicates += 1

    except Exception:
        logger.exception("Failed to ingest messages")

    if new_jobs > 0:
        logger.info("Enqueued %d new messages (duplicates=%d)", new_jobs, duplicates)
        return Response(status_code=200)

    if saw_messages and new_jobs == 0:
        return JSONResponse({"status": "duplicate", "duplicates": duplicates}, status_code=200)

    return Response(status_code=200)
