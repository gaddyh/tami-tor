from sqlalchemy.orm import Session

from adapters.primitivies import RawMessage
from handlers.errors import NonRetryableError
from models.inbound_message import InboundMessage
from models.work_item import WorkItem
from handlers.utility import load_or_create_session, load_business_by_id, now_israel, services_list_payload, ingest_inbound, format_date_time_for_template
from runtime.session_state import init_state, SessionState, SessionStep, SessionFlow, InputType, get_type
from models.session_state import Actor
from runtime.events import emit_event
from observability.obs import instrument_io
from handlers.wa_business_registry import wa_phone_id_registry
from handlers.models import Effect, HandlerResult, RouteKey, NoRouteFound, INBOUND_REGISTRY 
from datetime import datetime, date
from uuid import UUID
from enum import Enum
from typing import Any, Mapping
from effects.registry import dispatch_effect

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
    provider_id = business.get_default_provider_id()
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

            await dispatch_effect(
                kind=kind,
                eff=eff,
                db=db,
                inbound=inbound,
                wi=wi,
                session=session,
                state=state,
                adapter=adapter,
                business=business,
                provider_id=provider_id,
                client_name=client_name,
                service_id=service_id,
                service_name=service_name,
                chosen_start=chosen_start,
                chosen_end=chosen_end,
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
