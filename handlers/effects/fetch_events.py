# effects/handlers/fetch_events.py
from __future__ import annotations
from db.persist_event import persist_event_item, update_event_gcal
from adapters.google.fetch_events import get_future_events_verified
from tools.event_booking import format_events_message_he
from adapters.cloud_api import CloudAPIAdapter
from models.session import Session
from models.inbound_message import InboundMessage
from models.work_item import WorkItem

def _should_run(eff: dict) -> bool:
    return eff.get("to") == "client"

async def handle_fetch_events(*, eff: dict, provider_id, session:Session, inbound:InboundMessage, wi:WorkItem, adapter:CloudAPIAdapter, **_) -> None:
    if not _should_run(eff):
        return

    events = get_future_events_verified(
        provider_id=provider_id,
        client_id=wi.client_id,
        limit=10,
    )
    message = format_events_message_he(events)

    await adapter.send_message(
        recipient=wi.client_id,
        message=message,
    )
