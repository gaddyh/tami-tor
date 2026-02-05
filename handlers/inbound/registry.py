from ensurepip import bootstrap
from typing import Callable, Dict, Any, Optional, Tuple

from models.session_state import InputType, SessionFlow, SessionStep, SessionState, Actor
from handlers.inbound.client_show_services_list_list import client_show_services_list_list
from handlers.inbound.client_show_slots_list_list import client_show_slots_list_list
from handlers.inbound.client_confirm_btn_btn import client_confirm_btn_btn
from handlers.inbound.step_text import step_text
from adapters.primitivies import RawMessage
from handlers.models import Effect, HandlerResult, RouteKey, NoRouteFound, INBOUND_REGISTRY 
from observability.obs import instrument_io
from runtime.session_state import init_state, SessionState, SessionStep, SessionFlow, InputType, get_type
from models.business import Business
from adapters.cloud_api import CloudAPIAdapter
from agents.tami_core import get_llm_simple_reminders, ReminderBootstrap
from handlers.utility import llm_iso_to_utc

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
] = step_text

INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.SERVICE_PICK, InputType.TEXT, InputType.LIST_ID)
] = step_text

INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.SLOTS_PICK, InputType.TEXT, InputType.LIST_ID)
] = step_text

INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.CONFIRM, InputType.TEXT, InputType.BTN_ID)
] = step_text

INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.SERVICE_PICK, InputType.LIST_ID, InputType.LIST_ID)
] = client_show_services_list_list

INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.SLOTS_PICK, InputType.LIST_ID, InputType.LIST_ID)
] = client_show_slots_list_list

INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_CREATE, SessionStep.CONFIRM, InputType.BTN_ID, InputType.BTN_ID)
] = client_confirm_btn_btn

INBOUND_REGISTRY[
    (Actor.CLIENT, SessionFlow.CLIENT_DELETE, SessionStep.CLIENT_DELETE_PICK, InputType.TEXT, InputType.LIST_ID)
] = step_text