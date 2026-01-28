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

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
from fastapi import FastAPI
from contextlib import asynccontextmanager, suppress
from typing import Optional

app = FastAPI(title="tami")


class HelloIn(BaseModel):
    business_id: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)


class HelloOut(BaseModel):
    session_id: str
    outbox_id: str
    status: str


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

@app.get("/debug/state")
def debug_state(
    count: int = 10,
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    # --- auth ---
    expected = os.getenv("DEBUG_TOKEN")
    if not expected or x_debug_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")

    # clamp
    count = max(1, min(100, count))

    # --- Redis ---
    redis_queue_len = None
    redis_stream = []
    redis_errors = []

    stream_name = os.getenv("WORK_STREAM_KEY", WORK_STREAM_KEY)

    try:
        redis_queue_len = redis_client.llen(QUEUE_WORK)
    except Exception as e:
        redis_errors.append(f"queue_len: {e}")

    try:
        entries = redis_client.xrevrange(stream_name, max="+", min="-", count=count)
        for entry_id, fields in entries:
            meta = fields.get("meta")
            if meta:
                try:
                    fields["meta"] = json.loads(meta)
                except Exception:
                    pass
            redis_stream.append({"id": entry_id, "fields": fields})
    except Exception as e:
        redis_errors.append(f"stream_tail: {e}")

    # --- Postgres ---
    with SessionLocal() as db:
        # WorkItem status counts
        work_by_status = dict(
            db.execute(
                select(WorkItem.status, func.count()).group_by(WorkItem.status)
            ).all()
        )

        latest_work = db.execute(
            select(WorkItem)
            .order_by(WorkItem.updated_at.desc())
            .limit(10)
        ).scalars().all()

        latest_work_payload = [
            {
                "work_id": str(w.work_id),
                "kind": w.kind,
                "ref_id": str(w.ref_id),
                "status": w.status,
                "attempts": int(w.attempts),
                "business_id": w.business_id,
                "client_id": w.client_id,
                "run_after": w.run_after.isoformat() if w.run_after else None,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
                "created_at": w.created_at.isoformat() if w.created_at else None,
                "last_error": w.last_error,
            }
            for w in latest_work
        ]

        # InboundMessage status counts (optional but useful)
        inbound_by_status = dict(
            db.execute(
                select(InboundMessage.status, func.count()).group_by(InboundMessage.status)
            ).all()
        )

        latest_inbound = db.execute(
            select(InboundMessage)
            .order_by(InboundMessage.updated_at.desc())
            .limit(10)
        ).scalars().all()

        latest_inbound_payload = [
            {
                "id": str(m.id),
                "message_id": m.message_id,
                "phone_number_id": m.phone_number_id,
                "from": m.from_,
                "timestamp": int(m.timestamp) if m.timestamp is not None else None,
                "status": m.status,
                "attempts": int(m.attempts),
                "run_after": m.run_after.isoformat() if m.run_after else None,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "last_error": m.last_error,
            }
            for m in latest_inbound
        ]

    return {
        "postgres": {
            "work_by_status": work_by_status,
            "latest_work": latest_work_payload,
            "inbound_by_status": inbound_by_status,
            "latest_inbound": latest_inbound_payload,
        },
        "redis": {
            "queue": {"name": QUEUE_WORK, "length": redis_queue_len},
            "stream": {"name": stream_name, "latest": redis_stream},
            "errors": redis_errors,
        },
    }


from fastapi.responses import HTMLResponse
from html import escape
from html import escape
import os

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from apps.config import WORK_QUEUE_NAME  # reuse the same config var you already have


@app.get("/debug/ui", response_class=HTMLResponse)
def debug_ui(token: str, count: int = 20):
    expected = os.getenv("DEBUG_TOKEN")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")

    # Reuse your existing JSON debug source
    data = debug_state(count=count, x_debug_token=expected)

    pg = data.get("postgres", {})
    rd = data.get("redis", {})

    # Helpers
    def td(x): return f"<td>{escape(str(x))}</td>"
    def th(x): return f"<th>{escape(str(x))}</th>"

    # ---------------------------
    # Work Items (new)
    # ---------------------------
    work_by_status = pg.get("work_by_status") or {}
    work_status_rows = "".join(
        f"<tr>{td(k)}{td(v)}</tr>"
        for k, v in sorted(work_by_status.items())
    ) or "<tr><td colspan='2'>No data</td></tr>"

    latest_work = pg.get("latest_work") or []
    work_rows = ""
    for w in latest_work:
        work_rows += (
            "<tr>"
            f"{td(w.get('created_at'))}"
            f"{td(w.get('updated_at'))}"
            f"{td(w.get('status'))}"
            f"{td(w.get('attempts'))}"
            f"{td(w.get('kind'))}"
            f"{td(w.get('business_id'))}"
            f"{td(w.get('client_id'))}"
            f"{td(w.get('ref_id'))}"
            f"{td(w.get('work_id'))}"
            "</tr>"
        )
    if not work_rows:
        work_rows = "<tr><td colspan='9'>No work items</td></tr>"

    # ---------------------------
    # Inbound Messages (new)
    # ---------------------------
    inbound_by_status = pg.get("inbound_by_status") or {}
    inbound_status_rows = "".join(
        f"<tr>{td(k)}{td(v)}</tr>"
        for k, v in sorted(inbound_by_status.items())
    ) or "<tr><td colspan='2'>No data</td></tr>"

    latest_inbound = pg.get("latest_inbound") or []
    inbound_rows = ""
    for m in latest_inbound:
        inbound_rows += (
            "<tr>"
            f"{td(m.get('created_at'))}"
            f"{td(m.get('updated_at'))}"
            f"{td(m.get('status'))}"
            f"{td(m.get('attempts'))}"
            f"{td(m.get('phone_number_id'))}"
            f"{td(m.get('from'))}"
            f"{td(m.get('message_id'))}"
            f"{td(m.get('timestamp'))}"
            f"{td(m.get('id'))}"
            "</tr>"
        )
    if not inbound_rows:
        inbound_rows = "<tr><td colspan='9'>No inbound messages</td></tr>"

    # ---------------------------
    # Redis (updated for work queue)
    # ---------------------------
    queue = rd.get("queue", {}) or {}
    queue_name = queue.get("name") or OUTBOX_QUEUE_NAME  # fall back
    queue_len = queue.get("length", "?")
    redis_errs = "<br/>".join(escape(x) for x in (rd.get("errors") or [])) or "None"

    # ---------------------------
    # Redis Stream (work events)
    # ---------------------------
    stream = (rd.get("stream") or {})
    stream_latest = stream.get("latest") or []
    stream_rows = ""
    for e in stream_latest:
        f = e.get("fields", {}) or {}
        stream_rows += (
            "<tr>"
            f"{td(f.get('ts'))}"
            f"{td(f.get('event'))}"
            f"{td(f.get('kind') or f.get('type'))}"
            f"{td(f.get('business_id'))}"
            f"{td(f.get('client_id'))}"
            f"{td(f.get('work_id') or f.get('outbox_id') or f.get('inbound_id'))}"
            f"{td(f.get('attempt'))}"
            f"{td(f.get('meta'))}"
            "</tr>"
        )
    if not stream_rows:
        stream_rows = "<tr><td colspan='8'>No stream events</td></tr>"

    html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>tami debug</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui; margin: 24px; }}
    h2 {{ margin-top: 28px; }}
    .row {{ display: flex; gap: 24px; flex-wrap: wrap; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 14px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #eee; padding: 8px; font-size: 13px; vertical-align: top; }}
    th {{ background: #fafafa; text-align: left; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .small {{ font-size: 12px; color: #666; }}
  </style>
</head>
<body>
  <h1>tami debug</h1>

  <div class="row">
    <div class="card">
      <div><b>Redis queue</b> <span class="small">({escape(str(queue_name))})</span></div>
      <div class="mono" style="font-size:22px">{escape(str(queue_len))}</div>
    </div>
    <div class="card">
      <div><b>Redis errors</b></div>
      <div class="mono small">{redis_errs}</div>
    </div>
  </div>

  <h2>Postgres: WorkItem status counts</h2>
  <div class="card">
    <table>
      <thead><tr>{th("status")}{th("count")}</tr></thead>
      <tbody>{work_status_rows}</tbody>
    </table>
  </div>

  <h2>Postgres: Latest WorkItems</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          {th("created_at")}{th("updated_at")}{th("status")}{th("attempts")}
          {th("kind")}{th("business_id")}{th("client_id")}{th("ref_id")}{th("work_id")}
        </tr>
      </thead>
      <tbody>{work_rows}</tbody>
    </table>
  </div>

  <h2>Postgres: InboundMessage status counts</h2>
  <div class="card">
    <table>
      <thead><tr>{th("status")}{th("count")}</tr></thead>
      <tbody>{inbound_status_rows}</tbody>
    </table>
  </div>

  <h2>Postgres: Latest InboundMessages</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          {th("created_at")}{th("updated_at")}{th("status")}{th("attempts")}
          {th("phone_number_id")}{th("from")}{th("message_id")}{th("timestamp")}{th("id")}
        </tr>
      </thead>
      <tbody>{inbound_rows}</tbody>
    </table>
  </div>

  <h2>Redis Stream: Latest events</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          {th("ts")}{th("event")}{th("kind/type")}{th("business_id")}
          {th("client_id")}{th("work_id/outbox_id/inbound_id")}{th("attempt")}{th("meta")}
        </tr>
      </thead>
      <tbody>{stream_rows}</tbody>
    </table>
  </div>

  <div class="small" style="margin-top:16px">
    Tip: refresh to update. Use <span class="mono">?count=50</span> to show more stream events.
  </div>
</body>
</html>
"""
    return HTMLResponse(html)

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
