from __future__ import annotations

from typing import Any, Tuple

from adapters.primitivies import ContentType, RawMessage
from models.session_state import (
    SessionFlow,
    SessionState,
    SessionStep,
    DEFAULT_FLOW,
    DEFAULT_STEP,
    DEFAULT_VERSION,
    InputType
)
from observability.obs import instrument_io

@instrument_io(
    name="init_state",
    meta={"operation": "init_state"},
    input_fn=lambda session, rawMessage: {
        "session_id": str(session.session_id),
        "business_id": session.business_id or "",
        "client_id": session.client_id or "",
        "raw_message": rawMessage.model_dump(),
    },
    output_fn=lambda state: {
        "session_id": str(state.session_id),
        "business_id": state.business_id or "",
        "client_id": state.client_id or "",
        "flow": state.flow,
        "step": state.step,
        "input_type": state.input_type,
        "expected_type": state.expected_type,
        "data": state.data,
    },
    redact=True
)
def init_state(session: SessionState, rawMessage:RawMessage) -> SessionState:
    
    flow = SessionFlow.CLIENT_CREATE #TODO add flow_pick step or llm for text
    step = SessionStep.INIT

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
    
    return SessionState(
        flow=flow,
        step=step,
        input_type=type,
        expected_type=None,
        data=None
    )
    

