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


@app.post("/hello", response_model=HelloOut)
def hello(inp: HelloIn) -> HelloOut:
    """
    Stateless ingress:
    - creates/gets an active session
    - writes an outbox job
    - enqueues outbox_id to Redis
    """
    with SessionLocal() as db:
        # 1) find active session (simple rule: one active per client+business)
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
            db.flush()  # ensures session.session_id is available

        # 2) create outbox job
        outbox = Outbox(
            type="HELLO",
            business_id=inp.business_id,
            client_id=inp.client_id,
            session_id=session.session_id,
            payload_json={"text": "Hello from outbox"},
            status="pending",
        )
        db.add(outbox)
        db.commit()  # commit BEFORE enqueue (so worker can always find it)

        # 3) enqueue
        enqueue_outbox(str(outbox.outbox_id))

        return HelloOut(
            session_id=str(session.session_id),
            outbox_id=str(outbox.outbox_id),
            status="enqueued",
        )
