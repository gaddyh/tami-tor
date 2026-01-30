from sqlalchemy.orm import Session

from adapters.primitivies import RawMessage
from handlers.errors import NonRetryableError
from models.inbound_message import InboundMessage
from models.work_item import WorkItem
from adapters.cloud_api import CloudAPIAdapter
from handlers.utility import load_or_create_session, load_business_by_wa_id, now_israel, services_list_payload
from runtime.session_state import parse_session_state, dump_session_state
from reducers.client_reducer import reduce_session
from adapters.google.availability import get_available_slots, divide_slots_into_chunks, create_whatsapp_list_message
from apps.scheduled_message_ingest import persist_scheduled_message_and_enqueue
from datetime import timedelta
from models.availability import ChunkedAvailability
async def handle_process_inbound(db: Session, wi: WorkItem) -> None:
    """
    - load inbound message row via wi.ref_id
    - load/create session
    - reduce state
    - emit effects (e.g., create outbound rows / schedule sends)
    """
    if wi.kind != "INBOUND":
        raise NonRetryableError(f"handle_process_inbound got wrong kind: {wi.kind}")

    inbound = db.get(InboundMessage, wi.ref_id)
    if not inbound:
        # If the pointer is broken, retrying won't help.
        raise NonRetryableError(f"InboundMessage not found for ref_id={wi.ref_id}")

    # Now you have the durable row
    raw = inbound.raw or {}
    phone_number_id = inbound.phone_number_id
    from_ = inbound.from_
    message_id = inbound.message_id

    print(
        "Processing inbound work:",
        {"work_id": str(wi.work_id), "ref_id": str(wi.ref_id), "message_id": message_id, "from": from_},
        flush=True,
    )
    adapter = CloudAPIAdapter(phone_number_id)
    rawMessage: RawMessage = await adapter.parse_incoming(raw)
    print("Parsed message:", rawMessage, flush=True)

    session = load_or_create_session(
        db,
        business_id=wi.business_id,
        client_id=wi.client_id,
    )

    print(
        "Inbound routed to session",
        {
            "work_id": str(wi.work_id),
            "session_id": str(session.session_id),
            "business_id": session.business_id,
            "client_id": session.client_id,
        },
        flush=True,
    )

    # --- Understand / normalize state ---
    flow, step, data = parse_session_state(session.state_json)

    # Bootstrap if missing or malformed
    if not isinstance(session.state_json, dict) or not session.state_json:
        session.state_json = dump_session_state(flow, step, data)

    print(
        "Session state:",
        {
            "session_id": str(session.session_id),
            "flow": flow.value,
            "step": step.value,
            "data_keys": list(data.keys()),
        },
        flush=True,
    )

    business = load_business_by_wa_id(db, inbound.phone_number_id)

    ctx = {
        "is_provider": business.is_provider(from_),
        "services": business.services(),               # typed Pydantic list is OK
        "timezone": business.timezone,
        "booking_policy_mode": business.booking_policy_mode,
        "default_provider_id": business.get_default_provider_id(),
    }

    result = reduce_session(flow=flow, step=step, data=data, msg=rawMessage, ctx=ctx)
    session.state_json = dump_session_state(result.flow, result.step, result.data)
    
    print("Reducer result:", result, flush=True)

    try:

        for eff in result.effects:
            if eff["kind"] == "SEND_SERVICE_LIST" and eff.get("to") == "client":
                print("Sending service list", flush=True)
                payload = services_list_payload(eff["rows"])

                persist_scheduled_message_and_enqueue(
                    business_id=session.business_id,
                    wa_id=inbound.phone_number_id,                 # phone_number_id
                    client_id=session.client_id,                   # chat id
                    to_chat_id=from_,
                    interactive_payload=payload,
                    workflow_id=str(session.session_id),
                )

            if eff["kind"] == "SEND_SLOTS_LIST" and eff.get("to") == "client":
                print("Sending slots list", flush=True)
                now = now_israel()
                items = get_available_slots(
                    user_id=business.get_default_provider_id(),
                    timezone=business.timezone,
                    start_date=now.isoformat(),
                    end_date=(now + timedelta(days=2)).isoformat(),
                    duration=session.state_json["duration"],
                )
                print("Available slots:", items, flush=True)
                chunked: ChunkedAvailability = divide_slots_into_chunks(items, chunk_size=5)
                session.state_json["chunked"] = chunked
                session.state_json["chunk_index"] = 0

                payload = create_whatsapp_list_message(chunked, from_, 0)
                print("Sending slots payload:", payload, flush=True)
                result = await adapter.send_dynamic_list_message(to_phone=from_, interactive_payload=payload)
                print("Slots result:", result, flush=True)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Error processing message:", e, flush=True)
        raise
    # If this is a brand new session, you can initialize it explicitly:
    
    # don't commit here; let worker commit at the end

    # ... next: emit new work items, etc.
