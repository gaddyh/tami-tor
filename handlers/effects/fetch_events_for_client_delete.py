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
from runtime.events import emit_event

def _should_run(eff: dict) -> bool:
    return eff.get("to") == "client"

from typing import List

def build_verified_events_list_interactive_payload(
    events: List["VerifiedEvent"],
    *,
    header_text: str = "האירועים הקרובים שלך",
    body_text: str = "בחר אירוע לצפייה בפרטים",
    button_text: str = "הצג אירועים",
    section_title: str = "אירועים",
) -> dict:
    def fmt_time(row: "EventRow") -> str:
        if getattr(row, "all_day", False):
            if row.date and row.end_date:
                # end_date is exclusive in many schemas; keep it simple
                return f"{row.date.strftime('%d/%m/%Y')} – {row.end_date.strftime('%d/%m/%Y')}"
            if row.date:
                return row.date.strftime('%d/%m/%Y')
            return "יום שלם"

        if row.start_at and row.end_at:
            start = row.start_at.astimezone().strftime('%d/%m %H:%M')
            end = row.end_at.astimezone().strftime('%H:%M')
            return f"{start}–{end}"

        return "זמן לא ידוע"

    rows = []
    for ve in events:
        r = ve.row
        title = (r.title or "אירוע ללא כותרת")[:24]
        status = "✓" if ve.verified else "⚠️"
        desc = f"{fmt_time(r)} · {status}"[:72]

        rows.append(
            {
                "id": str(r.id),
                "title": title,
                "description": desc,
            }
        )

    # IMPORTANT: return the *interactive payload*, not the full message
    return {
        "type": "list",
        "header": {"type": "text", "text": header_text},
        "body": {"text": body_text},
        "action": {
            "button": button_text,
            "sections": [{"title": section_title, "rows": rows}],
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
    payload = build_verified_events_list_interactive_payload(events)

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