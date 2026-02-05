# effects/handlers/fetch_events.py
from __future__ import annotations
from db.persist_event import persist_event_item, update_event_gcal
from adapters.google.fetch_events import get_future_events_verified
from tools.event_booking import format_events_message_he
from adapters.cloud_api import CloudAPIAdapter
from models.session import Session
from models.inbound_message import InboundMessage
from models.work_item import WorkItem
from models.calendar_event import EventRow
from adapters.google.fetch_events import VerifiedEvent

def _should_run(eff: dict) -> bool:
    return eff.get("to") == "client"

from datetime import datetime, date
from typing import Optional

def _format_event_time(row: EventRow) -> str:
    if row.all_day:
        if row.date and row.end_date:
            if row.end_date > row.date:
                return f"{row.date.strftime('%d/%m/%Y')} – {row.end_date.strftime('%d/%m/%Y')}"
            return row.date.strftime('%d/%m/%Y')
        return "יום שלם"

    if row.start_at and row.end_at:
        start = row.start_at.astimezone().strftime('%d/%m %H:%M')
        end = row.end_at.astimezone().strftime('%H:%M')
        return f"{start}–{end}"

    return "זמן לא ידוע"

from typing import List

def build_verified_events_list_payload(
    events: List[VerifiedEvent],
    *,
    header_text: str = "האירועים הקרובים שלך",
    body_text: str = "בחר אירוע לצפייה בפרטים",
    button_text: str = "הצג אירועים",
    section_title: str = "אירועים",
) -> dict:
    rows = []

    for ve in events:
        row = ve.row

        title = row.title or "אירוע ללא כותרת"
        time_text = _format_event_time(row)

        if ve.verified:
            status_suffix = "✓"
        else:
            # keep it short, WhatsApp row description is limited
            status_suffix = "⚠️"

        description_parts = [time_text, status_suffix]
        description = " · ".join(filter(None, description_parts))

        rows.append(
            {
                "id": str(row.id),
                "title": title[:24],          # WhatsApp hard limit
                "description": description[:72],
            }
        )

    return {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": header_text,
            },
            "body": {
                "text": body_text,
            },
            "action": {
                "button": button_text,
                "sections": [
                    {
                        "title": section_title,
                        "rows": rows,
                    }
                ],
            },
        },
    }

async def handle_fetch_events_for_client_delete(*, eff: dict, provider_id, session:Session, inbound:InboundMessage, wi:WorkItem, adapter:CloudAPIAdapter, **_) -> None:
    if not _should_run(eff):
        return

    events = get_future_events_verified(
        provider_id=provider_id,
        client_id=wi.client_id,
        limit=10,
    )
    payload = build_verified_events_list_payload(events)

    res = await adapter.send_dynamic_list_message(
        to_phone=wi.client_id,
        interactive_payload=payload,
    )

    emit_event(
        event="INBOUND_FETCH_DELETE_EVENTS_LIST_SENT",
        inbound_id=str(wi.ref_id),
        type="INBOUND",
        business_id=str(session.business_id),
        client_id=str(session.client_id),
        session_id=str(session.session_id),
        meta={
            "work_id": str(wi.work_id),
            "to_phone": str(wi.client_id),
            "events_total": len(events or []),
            "send_ok": res["status"] == "sent",
        },
    )