# effects/handlers/send_confirm_buttons.py
from __future__ import annotations
from models.session_state import SessionState
from models.session import Session
from models.work_item import WorkItem
from adapters.cloud_api import CloudAPIAdapter
from models.availability import TimeSlot
from handlers.helper import build_hebrew_slot_confirmation
from runtime.events import emit_event
from handlers.helper import jsonify

def _should_run(eff: dict) -> bool:
    return eff.get("to") == "client"

async def handle_send_confirm_buttons(*, eff: dict, state:SessionState, wi:WorkItem, adapter:CloudAPIAdapter, session:Session, **_) -> None:
    if not _should_run(eff):
        return

    slot = TimeSlot.model_validate(state.data.chosen_slot)
    payload = build_hebrew_slot_confirmation(slot)

    await adapter.send_action_buttons(
        recipient=wi.client_id,
        message=payload,
    )

    emit_event(
        event="INBOUND_CONFIRM_BUTTONS_SENT",
        inbound_id=str(wi.ref_id),
        type="INBOUND",
        business_id=session.business_id,
        client_id=session.client_id,
        session_id=str(session.session_id),
        meta={
            "work_id": str(wi.work_id),
            "to_phone": wi.client_id,
            "state": jsonify(state.model_dump(mode="json")),
        },
    )
