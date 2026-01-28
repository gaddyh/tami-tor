# apps/webhook_ingest.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError

from db.session import SessionLocal
from models.inbound_message import InboundMessage
from models.work_item import WorkItem
from runtime.redis_client import enqueue_work
from runtime.events import emit_event


def _now_utc():
    return datetime.now(timezone.utc)


def persist_inbound_and_enqueue(
    *,
    message_id: str,
    phone_number_id: str,
    raw_message: dict,
) -> bool:
    if not message_id or not phone_number_id:
        raise ValueError("message_id and phone_number_id are required")

    # Extract compact fields exactly like you asked
    ts_raw = raw_message.get("timestamp")
    try:
        ts_int = int(ts_raw) if ts_raw is not None else None
    except (ValueError, TypeError):
        ts_int = None

    from_value = raw_message.get("from") or "unknown"

    inbound_id = None
    work_id = None

    with SessionLocal() as db:
        try:
            inbound = InboundMessage(
                message_id=message_id,
                phone_number_id=phone_number_id,
                raw=raw_message,
                timestamp=ts_int,
                from_=from_value,
            )
            db.add(inbound)
            db.flush()  # inbound.id

            inbound_id = inbound.id

            wi = WorkItem(
                kind="INBOUND",
                ref_id=inbound_id,
                business_id=phone_number_id,  # treat phone_number_id as business key for now
                client_id=from_value,
            )
            db.add(wi)
            db.flush()  # wi.work_id

            work_id = str(wi.work_id)
            db.commit()

        except IntegrityError:
            db.rollback()
            return False

    enqueue_work(work_id)

    emit_event(
        event="WORK_ENQUEUED",
        meta={
            "where": "webhook",
            "kind": "INBOUND",
            "work_id": work_id,
            "inbound_id": str(inbound_id),
            "phone_number_id": phone_number_id,
            "message_id": message_id,
            "from": from_value,
            "timestamp": ts_raw,
        },
    )

    return True
