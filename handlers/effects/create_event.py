# effects/handlers/create_event.py
from __future__ import annotations
from models.business import Business
from models.work_item import WorkItem
from models.event_item import EventItem
from tools.event_booking import create_event
from db.persist_event import persist_event_item, update_event_gcal
from datetime import datetime

async def handle_create_event(
    *,
    eff: dict,
    business:Business,
    wi:WorkItem,
    service_id:str,
    service_name:str,
    client_name:str,
    chosen_start:datetime,
    chosen_end:datetime,
    provider_id:str,
    **_,
) -> None:
    participants = []
    notify = False
    tz = business.timezone

    event = EventItem(
        item_id=None,
        command="create",
        service_id=service_id,
        title=service_name + " - " + (client_name or "") + " - " + (wi.client_id or ""),
        description=None,
        start_at=chosen_start,
        date=None,
        end_at=chosen_end,
        location="",
        participants=participants,
        recurrence=None,
        reminders=[],
        allow_conflicts=False,
        notify=notify,
        timezone=tz,
    )

    user_id = business.get_default_provider_id()
    event_id = persist_event_item(provider_id=user_id, client_id=wi.client_id, event=event)

    res = create_event(user_id=user_id, event=event)
    if res.get("ok"):
        gcal_event_id = res.get("item_id")
        update_event_gcal(user_id=wi.client_id, event_id=event_id, gcal_event_id=gcal_event_id)
    elif res.get("conflicts"):
        conflicts = res.get("conflicts")  # TODO
        # you may want to emit_event here or raise a typed exception
    else:
        raise Exception("Failed to create event")
