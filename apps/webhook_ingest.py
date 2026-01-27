# apps/webhook_ingest.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError

from db.session import SessionLocal
from models.inbound_message import InboundMessage
from runtime.redis_client import enqueue_inbound
from runtime.events import emit_event  # keep if you already have it


def _now_utc():
    return datetime.now(timezone.utc)


def persist_inbound_and_enqueue(
    *,
    message_id: str,
    phone_number_id: str,
    raw_message: dict,   # this is `m` (single WA message object)
) -> bool:
    """
    Returns:
      True  -> inserted new inbound msg + enqueued
      False -> duplicate inbound (already persisted)
    """
    if not message_id or not phone_number_id:
        raise ValueError("message_id and phone_number_id are required")

    inbound_id = None

    # Extract these exactly like you asked
    ts_raw = raw_message.get("timestamp")
    try:
        ts_int = int(ts_raw) if ts_raw is not None else None
    except (ValueError, TypeError):
        ts_int = None

    from_value = raw_message.get("from")
    if not from_value:
        # WhatsApp messages should have "from"; still allow but avoid null
        from_value = "unknown"

    with SessionLocal() as db:
        try:
            inbound = InboundMessage(
                message_id=message_id,
                phone_number_id=phone_number_id,
                raw=raw_message,
                timestamp=ts_int,
                from_=from_value,
                status="pending",
                attempts=0,
                run_after=None,
                last_error=None,
            )
            db.add(inbound)
            db.flush()  # assigns inbound.id
            inbound_id = str(inbound.id)
            db.commit()

        except IntegrityError:
            db.rollback()
            return False

    # Enqueue after commit (safe; cron can recover if enqueue fails)
    enqueue_inbound(inbound_id)

    # Optional observability hook (if you already have this stream)
    emit_event(
        event="INBOUND_ENQUEUED",
        inbound_id=inbound_id,
        meta={
            "phone_number_id": phone_number_id,
            "message_id": message_id,
            "from": from_value,
            "timestamp": ts_raw,
        },
    )

    return True
