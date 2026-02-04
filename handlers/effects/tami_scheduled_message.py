# handlers/scheduled_message.py
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import func

from handlers.errors import NonRetryableError
from models.work_item import WorkItem
from models.tami_scheduled_message import TamiScheduledMessage
from adapters.cloud_api import CloudAPIAdapter


async def handle_scheduled_message(db: Session, wi: WorkItem) -> None:
    if wi.kind != "SCHEDULED_MESSAGE":
        raise NonRetryableError(f"handle_scheduled_message got wrong kind: {wi.kind}")

    msg = db.get(TamiScheduledMessage, wi.ref_id)
    if not msg:
        raise NonRetryableError(
            f"TamiScheduledMessage not found for ref_id={wi.ref_id}"
        )

    # 🔒 Hard idempotency gate
    if msg.sent_at is not None:
        # already sent → success/no-op
        return

    if msg.status not in ("processing", "scheduled"):
        raise NonRetryableError(
            f"TamiScheduledMessage status={msg.status} not sendable for id={msg.id}"
        )

    adapter = CloudAPIAdapter(msg.wa_id)

    # 🔔 Send (this is the only non-DB side effect)
    await adapter.send_message(
        recipient=msg.to_chat_id,
        message=msg.message,
    )

    # ✅ Mark sent (DB is the source of truth)
    msg.status = "sent"
    msg.sent_at = func.now()
