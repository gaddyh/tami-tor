# effects/handlers/send_service_list.py
from __future__ import annotations
from handlers.utility import now_israel, services_list_payload
from runtime.events import emit_event
from models.session import Session
from models.work_item import WorkItem
from adapters.cloud_api import CloudAPIAdapter

def _should_run(eff: dict) -> bool:
    return eff.get("to") == "client"

async def handle_send_service_list(*, eff: dict, session:Session, inbound:InboundMessage, wi:WorkItem, adapter:CloudAPIAdapter, **_) -> None:
    if not _should_run(eff):
        return

    payload = services_list_payload(eff["rows"])

    await adapter.send_dynamic_list_message(
        to_phone=wi.client_id,
        interactive_payload=payload,
    )

    emit_event(
        event="INBOUND_SERVICE_LIST_SENT",
        inbound_id=str(wi.ref_id),
        type="INBOUND",
        business_id=session.business_id,
        client_id=session.client_id,
        session_id=str(session.session_id),
        meta={
            "work_id": str(wi.work_id),
            "rows": len(eff.get("rows") or []),
            "to_chat_id": wi.client_id,
        },
    )
