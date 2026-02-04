# effects/handlers/create_reminder.py
from __future__ import annotations
from adapters.cloud_api import CloudAPIAdapter
from db.message import persist_scheduled_message
from models.inbound_message import InboundMessage
from models.work_item import WorkItem

async def handle_create_reminder(*, eff: dict, db, inbound:InboundMessage, wi:WorkItem, client_name: str, adapter:CloudAPIAdapter, **_) -> None:
    title = eff.get("title", "")
    start = eff.get("start", "")

    persist_scheduled_message(
        db=db,
        wa_id=inbound.phone_number_id,
        to_chat_id=wi.client_id,
        message=title,
        send_at=start,
        type="reminder",
        to_name=client_name,
        idempotency_key=wi.work_id,
    )

    await adapter.send_message(
        recipient=wi.client_id,
        message=f"התזכורת  {title} נשמרה",
    )
