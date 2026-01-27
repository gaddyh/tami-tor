# apps/bot.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import select

from db.session import SessionLocal
from models.session import Session
from models.outbox import Outbox
from runtime.redis_client import enqueue_outbox

import os
import json
from fastapi import Header, HTTPException
from sqlalchemy import func
from runtime.redis_client import redis_client, QUEUE_OUTBOX

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
            event="OUTBOX_ENQUEUED",
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
            event="OUTBOX_PUSHED_REDIS",
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
    if count < 1:
        count = 1
    if count > 100:
        count = 100

    # --- Redis ---
    redis_queue_len = None
    redis_stream = []
    redis_errors = []

    try:
        redis_queue_len = redis_client.llen(QUEUE_OUTBOX)
    except Exception as e:
        redis_errors.append(f"queue_len: {e}")

    try:
        # last N events (newest first)
        entries = redis_client.xrevrange("events:outbox", max="+", min="-", count=count)
        for entry_id, fields in entries:
            # fields are strings; try to parse meta if present
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
        outbox_by_status = dict(
            db.execute(
                select(Outbox.status, func.count()).group_by(Outbox.status)
            ).all()
        )

        latest_outbox = db.execute(
            select(Outbox)
            .order_by(Outbox.updated_at.desc())
            .limit(5)
        ).scalars().all()

        latest_outbox_payload = [
            {
                "outbox_id": str(o.outbox_id),
                "type": o.type,
                "status": o.status,
                "attempts": int(o.attempts),
                "business_id": o.business_id,
                "client_id": o.client_id,
                "session_id": str(o.session_id),
                "run_after": o.run_after.isoformat() if o.run_after else None,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in latest_outbox
        ]

    return {
        "postgres": {
            "outbox_by_status": outbox_by_status,
            "latest_outbox": latest_outbox_payload,
        },
        "redis": {
            "queue": {"name": QUEUE_OUTBOX, "length": redis_queue_len},
            "stream": {"name": "events:outbox", "latest": redis_stream},
            "errors": redis_errors,
        },
    }
