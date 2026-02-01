from typing import Callable, Dict, Any, Optional, Tuple

from models.session_state import InputType, SessionFlow, SessionStep, SessionState, Actor
from handlers.client.create.client_show_services_list_list import client_show_services_list_list
from handlers.client.create.client_show_slots_list_list import client_show_slots_list_list
from handlers.client.create.client_confirm_btn_btn import client_confirm_btn_btn
from handlers.client.create.init_text import init_text
from models.session import Session

from adapters.primitivies import RawMessage
from handlers.models import Effect, HandlerResult, RouteKey, NoRouteFound, INBOUND_REGISTRY 
from observability.obs import instrument_io

@instrument_io(
    name="dispatch",
    meta={"operation": "dispatch"},
    input_fn=lambda session, msg, ctx: {
        "work_id": str(session.session_id),
        "business_id": session.business_id or "",
        "client_id": session.client_id or "",
        "flow": session.state_json["flow"],
        "step": session.state_json["step"],
        "ctx": ctx,
    },
    output_fn=lambda result: result,
    redact=True
)
def dispatch(session: Session, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    state = SessionState.model_validate(session.state_json)

    exact_key: RouteKey = (state.actor, state.flow, state.step, state.input_type, state.expected_type)
    handler = INBOUND_REGISTRY.get(exact_key)

    if handler is None:
        raise NoRouteFound(f"No handler registered for {exact_key}")

    return handler(state, msg, ctx)


INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.INIT, InputType.TEXT, InputType.TEXT)
] = init_text

INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.SERVICE_PICK, InputType.LIST_ID, InputType.LIST_ID)
] = client_show_services_list_list

INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.SLOTS_PICK, InputType.LIST_ID, InputType.LIST_ID)
] = client_show_slots_list_list

INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.CONFIRM, InputType.TEXT, InputType.TEXT)
] = client_confirm_btn_btn