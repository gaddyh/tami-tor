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
