# handlers/scheduled.py
from __future__ import annotations

from sqlalchemy.orm import Session

from handlers.errors import NonRetryableError
from models.work_item import WorkItem
from models.business_scheduled_message import BusinessScheduledMessage
from adapters.cloud_api import CloudAPIAdapter


async def handle_dynamic_list(db: Session, wi: WorkItem) -> None:
    if wi.kind != "DYNAMIC_LIST":
        raise NonRetryableError(f"handle_dynamic_list got wrong kind: {wi.kind}")

    msg = db.get(BusinessScheduledMessage, wi.ref_id)
    if not msg:
        raise NonRetryableError(f"BusinessScheduledMessage not found for ref_id={wi.ref_id}")

    adapter = CloudAPIAdapter(msg.wa_id)

    await adapter.send_dynamic_list_message(
        to_phone=msg.to_chat_id,
        interactive_payload=msg.interactive_payload,
    )

    # optional: update status for audit
    msg.status = "sent"