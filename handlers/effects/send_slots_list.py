# effects/handlers/send_slots_list.py
from __future__ import annotations
from datetime import timedelta
from models.session_state import SessionState, SessionStep, InputType
from models.session import Session
from models.work_item import WorkItem
from adapters.cloud_api import CloudAPIAdapter
from models.business import Business
from adapters.google.availability import get_available_slots, divide_chunked_into_slots, is_exact_start_match
from models.availability import ChunkedAvailability
from models.availability import TimeSlot
from handlers.utility import now_israel
from handlers.helper import build_hebrew_slot_confirmation, create_whatsapp_list_message
from runtime.events import emit_event
from handlers.helper import jsonify

def _should_run(eff: dict) -> bool:
    return eff.get("to") == "client"

async def handle_send_slots_list(*, eff: dict, state:SessionState, provider_id, business:Business, wi:WorkItem, adapter:CloudAPIAdapter, session:Session, **_) -> None:
    if not _should_run(eff):
        return

    bootstrap_start_dt = state.data.bootstrap_start_dt
    bootstrap_end_dt = state.data.bootstrap_end_dt
    now = bootstrap_start_dt or now_israel()
    end_date = bootstrap_end_dt or (now + timedelta(days=4))

    items = get_available_slots(
        user_id=provider_id,
        timezone=business.timezone,
        start_date=now.isoformat(),
        end_date=end_date.isoformat(),
        duration=state.data.duration,
    )

    if len(items) == 0:
        await adapter.send_message(
            recipient=wi.client_id,
            message="אין זמינות",
        )
        return

    if bootstrap_start_dt:
        try:
            if is_exact_start_match(items, bootstrap_start_dt):
                chunked: ChunkedAvailability = divide_chunked_into_slots(items, chunk_size=5)
                chosen = chunked.chunks[0].slots[0]
                slot = TimeSlot.model_validate(chosen)

                state.data.chosen_slot = slot
                state.step = SessionStep.CONFIRM
                state.error_message = None
                state.expected_type = InputType.BTN_ID

                payload = build_hebrew_slot_confirmation(slot)
                session.state_json = jsonify(state.model_dump(mode="json"))

                await adapter.send_action_buttons(
                    recipient=wi.client_id,
                    message=payload,
                )
                return
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Failed to match bootstrap start: {e}")

    chunked: ChunkedAvailability = divide_chunked_into_slots(items, chunk_size=5)
    state.data.chunked = jsonify(chunked.model_dump(mode="json"))
    state.data.chunked_index = 0

    payload = create_whatsapp_list_message(chunked, wi.client_id, 0)
    res = await adapter.send_dynamic_list_message(
        to_phone=wi.client_id,
        interactive_payload=payload,
    )

    emit_event(
        event="INBOUND_SLOTS_LIST_SENT",
        inbound_id=str(wi.ref_id),
        type="INBOUND",
        business_id=str(session.business_id),
        client_id=str(session.client_id),
        session_id=str(session.session_id),
        meta={
            "work_id": str(wi.work_id),
            "to_phone": str(wi.client_id),
            "slots_total": len(items or []),
            "send_ok": res["status"] == "sent",
            "state": state.model_dump(mode="json"),
        },
    )
