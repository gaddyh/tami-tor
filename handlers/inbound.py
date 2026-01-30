from sqlalchemy.orm import Session

from adapters.primitivies import RawMessage
from handlers.errors import NonRetryableError
from models.inbound_message import InboundMessage
from models.work_item import WorkItem
from adapters.cloud_api import CloudAPIAdapter
from handlers.utility import load_or_create_session, load_business_by_wa_id, now_israel, services_list_payload
from runtime.session_state import parse_session_state, dump_session_state
from reducers.client_reducer import reduce_session
from adapters.google.availability import get_available_slots, divide_chunked_into_slots, create_whatsapp_list_message
from apps.scheduled_message_ingest import persist_scheduled_message_and_enqueue
from datetime import timedelta
from models.availability import ChunkedAvailability
from reducers.helper import build_hebrew_slot_confirmation
from runtime.events import emit_event_with_langfuse
from models.availability import TimeSlot
from observability.obs import instrument_io

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

    emit_event_with_langfuse(
        event="INBOUND_HANDLER_START",
        meta={
            "work_id": str(wi.work_id),
            "ref_id": str(wi.ref_id),
            "business_id": wi.business_id or "",
            "client_id": wi.client_id or "",
        },
    )

    inbound = db.get(InboundMessage, wi.ref_id)
    if not inbound:
        raise NonRetryableError(f"InboundMessage not found for ref_id={wi.ref_id}")

    raw = inbound.raw or {}
    phone_number_id = inbound.phone_number_id
    from_ = inbound.from_
    message_id = inbound.message_id

    emit_event_with_langfuse(
        event="INBOUND_ROW_LOADED",
        meta={
            "work_id": str(wi.work_id),
            "message_id": message_id,
            "from": from_,
            "phone_number_id": phone_number_id,
        },
    )

    adapter = CloudAPIAdapter(phone_number_id)
    rawMessage: RawMessage = await adapter.parse_incoming(raw)

    emit_event_with_langfuse(
        event="INBOUND_PARSED",
        meta={
            "work_id": str(wi.work_id),
            "message_id": message_id,
            "msg_type": getattr(rawMessage, "type", None) or rawMessage.__class__.__name__,
        },
    )

    session = load_or_create_session(
        db,
        business_id=wi.business_id,
        client_id=wi.client_id,
    )

    emit_event_with_langfuse(
        event="INBOUND_SESSION_LOADED",
        meta={
            "work_id": str(wi.work_id),
            "session_id": str(session.session_id),
            "business_id": session.business_id,
            "client_id": session.client_id,
            "state": session.state_json,
        },
    )

    flow, step, data = parse_session_state(session.state_json)

    if not isinstance(session.state_json, dict) or not session.state_json:
        session.state_json = dump_session_state(flow, step, data)
        emit_event_with_langfuse(
            event="INBOUND_SESSION_STATE_BOOTSTRAPPED",
            meta={"work_id": str(wi.work_id), "session_id": str(session.session_id),"state": session.state_json}
        )

    business = load_business_by_wa_id(db, inbound.phone_number_id)

    ctx = {
        "is_provider": business.is_provider(from_),
        "services": business.services(),
        "timezone": business.timezone,
        "booking_policy_mode": business.booking_policy_mode,
        "default_provider_id": business.get_default_provider_id(),
    }

    result = reduce_session(flow=flow, step=step, data=data, msg=rawMessage, ctx=ctx)
    session.state_json = dump_session_state(result.flow, result.step, result.data)

    emit_event_with_langfuse(
        event="INBOUND_REDUCED",
        meta={
            "work_id": str(wi.work_id),
            "session_id": str(session.session_id),
            "flow": result.flow.value,
            "step": result.step.value,
            "effects_count": len(result.effects or []),
            "state": session.state_json,
        },
    )

    try:
        for eff in result.effects or []:
            kind = eff.get("kind", "UNKNOWN_EFFECT")

            emit_event_with_langfuse(
                event="INBOUND_EFFECT_EMITTED",
                meta={
                    "work_id": str(wi.work_id),
                    "session_id": str(session.session_id),
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
                    to_chat_id=from_,
                    interactive_payload=payload,
                    workflow_id=str(session.session_id),
                )

                emit_event_with_langfuse(
                    event="INBOUND_SERVICE_LIST_ENQUEUED",
                    meta={
                        "work_id": str(wi.work_id),
                        "session_id": str(session.session_id),
                        "rows": len(eff.get("rows") or []),
                        "to_chat_id": from_,
                    },
                )

            if kind == "SEND_SLOTS_LIST" and eff.get("to") == "client":
                now = now_israel()
                items = get_available_slots(
                    user_id=business.get_default_provider_id(),
                    timezone=business.timezone,
                    start_date=now.isoformat(),
                    end_date=(now + timedelta(days=4)).isoformat(),
                    duration=session.state_json["data"]["duration"],
                )
                chunked: ChunkedAvailability = divide_chunked_into_slots(items, chunk_size=5)
                session.state_json["data"]["chunked"] = chunked.model_dump()
                session.state_json["data"]["chunk_index"] = 0

                payload = create_whatsapp_list_message(chunked, from_, 0)
                send_result = await adapter.send_dynamic_list_message(to_phone=from_, interactive_payload=payload)

                emit_event_with_langfuse(
                    event="INBOUND_SLOTS_LIST_SENT",
                    meta={
                        "work_id": str(wi.work_id),
                        "session_id": str(session.session_id),
                        "to_phone": from_,
                        "slots_total": len(items or []),
                        # keep it light; don’t dump full API responses into metadata
                        "send_ok": bool(send_result),
                        "state": session.state_json,
                    },
                )

            if kind == "SEND_CONFIRM_BUTTONS" and eff.get("to") == "client":
                slot = session.state_json["data"]["slot"]
                slot = TimeSlot.model_validate(slot)
                payload = build_hebrew_slot_confirmation(slot)
                await adapter.send_action_buttons(
                    recipient=from_,
                    message=payload,
                )

                emit_event_with_langfuse(
                    event="INBOUND_CONFIRM_BUTTONS_SENT",
                    meta={
                        "work_id": str(wi.work_id),
                        "session_id": str(session.session_id),
                        "to_phone": from_,
                        "state": session.state_json,
                    },
                )

        emit_event_with_langfuse(
            event="INBOUND_HANDLER_DONE",
            meta={"work_id": str(wi.work_id), "session_id": str(session.session_id), "state": session.state_json},
        )

        return session.state_json #for observability

    except Exception as e:
        emit_event_with_langfuse(
            event="INBOUND_HANDLER_ERROR",
            meta={
                "work_id": str(wi.work_id),
                "ref_id": str(wi.ref_id),
                "error": str(e),
                "state": session.state_json,
            },
        )
        raise
