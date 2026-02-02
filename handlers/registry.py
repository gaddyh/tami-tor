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
from runtime.session_state import init_state, SessionState, SessionStep, SessionFlow, InputType, get_type
from models.business import Business
from adapters.cloud_api import CloudAPIAdapter

tami_wa_id = "723503380842690"
tami_dev_wa_id = "816205444920021"
tami_tor_wa_id = "982974261547358"

def tami_handler(state: SessionState, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    return dispatch(state, msg, ctx)

def tami_dev_handler(business: Business, is_provider: bool, state_json: dict[str, Any], rawMessage: RawMessage, adapter: CloudAPIAdapter) -> HandlerResult:
    if not state_json:
        state = init_state(rawMessage, actor=Actor.PROVIDER if is_provider else Actor.CLIENT)
    else:
        state = SessionState.model_validate(state_json)

    ctx = {
        "is_provider": is_provider,
        "services": business.services(),
        "timezone": business.timezone,
        "booking_policy_mode": business.booking_policy_mode,
        "default_provider_id": business.get_default_provider_id(),
    }

    state.input_type = get_type(rawMessage)

    result = dispatch(state=state, msg=rawMessage, ctx=ctx)

    return result

def tami_tor_handler(state: SessionState, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    return dispatch(state, msg, ctx)

wa_phone_id_registry = {
    tami_wa_id: tami_handler,
    tami_dev_wa_id: tami_dev_handler,
    tami_tor_wa_id: tami_tor_handler,
}

@instrument_io(
    name="dispatch",
    meta={"operation": "dispatch"},
    input_fn=lambda state, msg, ctx: {
        "state": state,
        "ctx": ctx,
    },
    output_fn=lambda result: result,
    redact=True
)
def dispatch(state: SessionState, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
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
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.CONFIRM, InputType.BTN_ID, InputType.BTN_ID)
] = client_confirm_btn_btn