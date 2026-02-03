from sqlalchemy.orm import Session

from adapters.primitivies import RawMessage
from handlers.errors import NonRetryableError
from models.inbound_message import InboundMessage
from models.work_item import WorkItem
from handlers.utility import load_or_create_session, load_business_by_id, now_israel, services_list_payload, ingest_inbound, format_date_time_for_template
from runtime.session_state import init_state, SessionState, SessionStep, SessionFlow, InputType, get_type
from models.session_state import Actor
from adapters.google.availability import get_available_slots, divide_chunked_into_slots, create_whatsapp_list_message
from apps.scheduled_message_ingest import persist_scheduled_message_and_enqueue
from datetime import timedelta
from models.availability import ChunkedAvailability
from reducers.helper import build_hebrew_slot_confirmation
from runtime.events import emit_event
from models.availability import TimeSlot
from observability.obs import instrument_io
from handlers.registry import dispatch, wa_phone_id_registry
from models.event_item import EventItem
from tools.event_booking import create_event
from handlers.models import Effect, HandlerResult, RouteKey, NoRouteFound, INBOUND_REGISTRY 
from db.persist_event import persist_event_item, update_event_item
from db.fetch_events import fetch_future_events_as_dicts
from tools.event_booking import format_events_message_he

from datetime import datetime, date
from uuid import UUID
from enum import Enum
from typing import Any, Mapping

def jsonify(x: Any) -> Any:
    if x is None or isinstance(x, (str, int, float, bool)):
        return x
    if isinstance(x, (datetime, date)):
        return x.isoformat()
    if isinstance(x, UUID):
        return str(x)
    if isinstance(x, Enum):
        return x.value
    if isinstance(x, Mapping):
        return {str(k): jsonify(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [jsonify(v) for v in x]
    return str(x)


@instrument_io(
    name="handle_process_inbound",
    meta={"operation": "handle_process_inbound"},
    input_fn=lambda db, wi: {
        "work_id": str(wi.work_id),
        "ref_id": str(wi.ref_id),
        "business_id": wi.business_id or "",
        "client_id": wi.client_id or ""
    },
    output_fn=lambda result: result,
    redact=True
)
async def handle_process_inbound(db: Session, wi: WorkItem) -> dict | None:
    if wi.kind != "INBOUND":
        raise NonRetryableError(f"handle_process_inbound got wrong kind: {wi.kind}")

    inbound = db.get(InboundMessage, wi.ref_id)
    if not inbound:
        raise NonRetryableError(f"InboundMessage not found for ref_id={wi.ref_id}")

    rawMessage, adapter = await ingest_inbound(inbound, wi)

    wa_phone_id_handler = wa_phone_id_registry.get(inbound.phone_number_id)
    if not wa_phone_id_handler:
        raise NonRetryableError(f"No handler found for phone_number_id={inbound.phone_number_id}")
    
    session = load_or_create_session(db, business_id=wi.business_id, client_id=wi.client_id)
    business = load_business_by_id(db, wi.business_id)
    is_provider = business.is_provider(wi.client_id)
    result:HandlerResult = wa_phone_id_handler(business, is_provider, session.state_json, rawMessage, adapter)
   
    state = result.state
    try:
        for eff in result.effects or []:
            kind = eff.get("kind", "UNKNOWN_EFFECT")
            service_id = state.data.service_id
            service_name = state.data.service_name
            client_name = state.data.client_name
            duration = state.data.duration
            chosen_slot = state.data.chosen_slot
            if chosen_slot:
                chosen_start = chosen_slot.start
                chosen_end = chosen_slot.end

            emit_event(
                event="INBOUND_EFFECT_EMITTED",
                inbound_id=str(wi.ref_id),
                type="INBOUND",
                business_id=session.business_id,
                client_id=session.client_id,
                session_id=str(session.session_id),
                meta={
                    "work_id": str(wi.work_id),
                    "effect_kind": kind,
                    "to": eff.get("to", ""),
                },
            )

            if kind == "SEND_SERVICE_LIST" and eff.get("to") == "client":
                payload = services_list_payload(eff["rows"])

                persist_scheduled_message_and_enqueue(
                    business_id=session.business_id,
                    wa_id=inbound.phone_number_id,
                    client_id=session.client_id,
                    to_chat_id=wi.client_id,
                    interactive_payload=payload,
                    workflow_id=str(session.session_id),
                    send_at=now_israel(),
                    to_name="client_name",
                    idempotency_key=wi.work_id,
                )

                emit_event(
                    event="INBOUND_SERVICE_LIST_ENQUEUED",
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

            if kind == "FETCH_EVENTS" and eff.get("to") == "client":
                events = fetch_future_events_as_dicts(user_id=wi.client_id, limit=10)
                message = format_events_message_he(events)
                await adapter.send_message(
                    recipient=wi.client_id,
                    message=message,
                )

            if kind == "SEND_SLOTS_LIST" and eff.get("to") == "client":
                bootstrap_start_dt = state.data.bootstrap_start_dt
                bootstrap_end_dt = state.data.bootstrap_end_dt
                now = bootstrap_start_dt or now_israel()
                end_date = bootstrap_end_dt or (now + timedelta(days=4))
                items = get_available_slots(
                    user_id=business.get_default_provider_id(),
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


            if kind == "SEND_CONFIRM_BUTTONS" and eff.get("to") == "client":
                slot = state.data.chosen_slot
                slot = TimeSlot.model_validate(slot)
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

            if kind == "CREATE_EVENT":
                participants = []
                notify = False
                tz = business.timezone
                event = EventItem(
                    item_id=None,
                    command="create",
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
                event_id = persist_event_item(user_id=user_id, event=event)
                res = create_event(user_id=user_id, event=event)
                if res.get("ok"):
                    gcal_event_id = res.get("item_id")
                    update_event_item(user_id=user_id, event=event, event_id=event_id, gcal_event_id=gcal_event_id)
                elif res.get("conflicts"):
                    conflicts = res.get("conflicts") #TODO
                else:
                    raise Exception("Failed to create event")





            if kind == "SEND_CONFIRMATION" and eff.get("to") == "client":
                res = await adapter.send_message(
                        recipient=wi.client_id,
                        message=eff.get("text", ""),
                    )

        session.state_json = jsonify(state.model_dump(mode="json"))
        if state.step == SessionStep.DONE:
            debug = session.state_json
            session.state_json = {}

        emit_event(
            event="INBOUND_HANDLER_DONE",
            inbound_id=str(wi.ref_id),
            type="INBOUND",
            business_id=session.business_id,
            client_id=session.client_id,
            session_id=str(session.session_id),
            meta={
                "work_id": str(wi.work_id),
                "state": jsonify(session.state_json),
            },
        )

        return session.state_json or debug  # for observability

    except Exception as e:
        import traceback
        traceback.print_exc()
        emit_event(
            event="INBOUND_HANDLER_ERROR",
            inbound_id=str(wi.ref_id),
            type="INBOUND",
            business_id=session.business_id,
            client_id=session.client_id,
            session_id=str(session.session_id),
            meta={
                "work_id": str(wi.work_id),
                "ref_id": str(wi.ref_id),
                "error": str(e),
                "state": jsonify(session.state_json),
            },
        )
        raise
