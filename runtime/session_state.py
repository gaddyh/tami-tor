from __future__ import annotations

from typing import Any, Tuple

from adapters.primitivies import ContentType, RawMessage
from models.session_state import (
    Actor,
    SessionFlow,
    SessionState,
    SessionStep,
    DEFAULT_FLOW,
    DEFAULT_STEP,
    DEFAULT_VERSION,
    InputType,
    SessionData,
)
from observability.obs import instrument_io



def get_type(rawMessage: RawMessage) -> InputType:
    type = rawMessage.content.type if rawMessage.content.type in ["text", "audio", "interactive", "contacts", "button"] else "unsupported"

    if type == "text":
        type = InputType.TEXT
    elif type == "audio":
        type = InputType.AUDIO
    elif type == "interactive":
        if rawMessage.content.button_reply:
            type = InputType.BTN_ID
        elif rawMessage.content.list_reply:
            type = InputType.LIST_ID

    return type


@instrument_io(
    name="init_state",
    meta={"operation": "init_state"},
    input_fn=lambda rawMessage, actor: {
        "raw_message": rawMessage.model_dump(),
        "actor": actor,
    },
    output_fn=lambda state: {
        "state": state.model_dump(),
    },
    redact=True
)
def init_state(rawMessage:RawMessage, actor:Actor) -> SessionState:
    
    flow = SessionFlow.CLIENT_CREATE #TODO add flow_pick step or llm for text
    step = SessionStep.INIT

    type = get_type(rawMessage)

    return SessionState(
        actor=Actor.CLIENT, #TODO change to actor after debugging
        flow=flow,
        step=step,
        input_type=type,
        expected_type=InputType.TEXT,
        data=SessionData(),
    )
    

