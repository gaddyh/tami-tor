from typing import Dict, Any

from models.session_state import InputType, SessionFlow, SessionStep, SessionState, Actor
from adapters.primitivies import RawMessage
from handlers.models import HandlerResult, INBOUND_REGISTRY 
from observability.obs import instrument_io
from runtime.session_state import init_state, SessionState, SessionStep, SessionFlow, InputType, get_type
from models.business import Business
from adapters.cloud_api import CloudAPIAdapter
from agents.tami_core import get_llm_simple_reminders, ReminderBootstrap
from handlers.utility import llm_iso_to_utc
from handlers.inbound.registry import dispatch

tami_wa_id = "723503380842690"
tami_dev_wa_id = "816205444920021"
tami_tor_wa_id = "982974261547358"

def tami_handler(business: Business, is_provider: bool, state_json: dict[str, Any], rawMessage: RawMessage, adapter: CloudAPIAdapter) -> HandlerResult:
    
    if not state_json:
        state = init_state(rawMessage, actor=Actor.CLIENT) #TODO
    else:
        state = SessionState.model_validate(state_json)
    
    effects = []
    text = rawMessage.content.text.strip()
    if "תזכיר" in text:
        bootstrap: ReminderBootstrap = get_llm_simple_reminders(text)

        if bootstrap.start and bootstrap.title:
            start = llm_iso_to_utc(bootstrap.start)

            end = llm_iso_to_utc(bootstrap.end) if bootstrap.end else None

            effects.append({
                "kind": "CREATE_REMINDER",
                "title": bootstrap.title,
                "start": start,   # tz-aware UTC datetime
                "end": end,       # tz-aware UTC datetime or None
            })

        return HandlerResult(
            state=state,
            effects=effects,
        )
    return HandlerResult(
        state=state,
        effects=[],
    )

def tami_dev_handler(business: Business, is_provider: bool, state_json: dict[str, Any], rawMessage: RawMessage, adapter: CloudAPIAdapter) -> HandlerResult:
    if not state_json:
        state = init_state(rawMessage, actor=Actor.CLIENT) #TODO
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

def tami_tor_handler(business: Business, is_provider: bool, state_json: dict[str, Any], rawMessage: RawMessage, adapter: CloudAPIAdapter) -> HandlerResult:
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

wa_phone_id_registry = {
    tami_wa_id: tami_handler,
    tami_dev_wa_id: tami_dev_handler,
    tami_tor_wa_id: tami_tor_handler,
}
