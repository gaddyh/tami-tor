# apps/webhook_ingest.py
from __future__ import annotations

import uuid
from typing import Optional
from sqlalchemy.exc import IntegrityError

from db.session import SessionLocal
from db.models.inbound_message import InboundMessage


def persist_inbound(
    *,
    message_id: str,
    phone_number_id: str,
    raw_message: dict,
) -> tuple[bool, Optional[uuid.UUID], str]:
    """
    Persist inbound message for auditing/debug + dedup.

    Returns:
      (inserted, inbound_db_id, from_value)

    NOTE:
      Dedup relies on a UNIQUE constraint on (phone_number_id, message_id).
    """
    if not message_id or not phone_number_id:
        raise ValueError("message_id and phone_number_id are required")

    ts_raw = raw_message.get("timestamp")
    try:
        ts_int = int(ts_raw) if ts_raw is not None else None
    except (ValueError, TypeError):
        ts_int = None

    from_value = (raw_message.get("from") or "unknown").strip() or "unknown"

    inbound_id: Optional[uuid.UUID] = None

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
            db.flush()  # assigns inbound.id (UUID)
            inbound_id = inbound.id
            db.commit()
            return True, inbound_id, from_value

        except IntegrityError:
            db.rollback()
            return False, None, from_value
