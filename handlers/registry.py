from typing import Callable, Dict, Any, Optional, Tuple

from models.session_state import InputType, SessionFlow, SessionStep, SessionState
from handlers.client.create.show_slots_btn_text import client_show_slots_btn_text
from handlers.client.create.show_slots_btn_btn import client_show_slots_btn_btn
from handlers.client.create.init_text import init_text
from models.session import Session

from adapters.primitivies import RawMessage
from handlers.models import Effect, HandlerResult, RouteKey, NoRouteFound, INBOUND_REGISTRY 

@instrument_io(
    name="dispatch",
    meta={"operation": "dispatch"},
    input_fn=lambda session, msg, ctx: {
        "work_id": str(session.session_id),
        "ref_id": str(msg.message_id),
        "business_id": session.business_id or "",
        "client_id": session.client_id or ""
    },
    output_fn=lambda result: result,
    redact=True
)
def dispatch(session: Session, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    state = SessionState.model_validate(session.state_json)

    exact_key: RouteKey = (state.flow, state.step, state.input_type, state.expected_type)
    handler = INBOUND_REGISTRY.get(exact_key)

    # fallback: wildcard expected_type
    if handler is None:
        wildcard_key: RouteKey = (state.flow, state.step, state.input_type, None)
        handler = INBOUND_REGISTRY.get(wildcard_key)

    if handler is None:
        raise NoRouteFound(f"No handler registered for {exact_key}")

    return handler(session, msg, ctx)


INBOUND_REGISTRY[
    (SessionFlow.CLIENT_CREATE, SessionStep.SLOTS_PICK, InputType.BTN_ID, InputType.BTN_ID)
] = client_show_slots_btn_btn

# wildcard expected_type for init_text
INBOUND_REGISTRY[
    (SessionFlow.CLIENT_CREATE, SessionStep.INIT, InputType.TEXT, None)
] = init_text
