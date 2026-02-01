from models.session_state import SessionState, SessionStep, InputType
from handlers.models import HandlerResult, Effect
from adapters.primitivies import RawMessage
from typing import Any
from observability.obs import instrument_io
from handlers.utility import build_service_rows

@instrument_io(
    name="init_text",
    meta={"operation": "init_text"},
    input_fn=lambda state, msg, ctx: {
        "state": state,
        "ctx": ctx,
    },
    output_fn=lambda result: result,
    redact=True
)
def init_text(state: SessionState, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    print("init_text ", state)
    effects: list[Effect] = []
    services = ctx.get("services") or []
    if not services:
        effects.append({"kind": "SEND_TEXT", "to": "client", "text": "אין שירותים זמינים כרגע."})
        return HandlerResult(state=state, effects=effects)

    state.step = SessionStep.SERVICE_PICK
    state.input_type = InputType.LIST_ID
    state.expected_type = InputType.LIST_ID
    effects.append({"kind": "SEND_SERVICE_LIST", "to": "client", "rows": build_service_rows(services)})
    
    return HandlerResult(state=state, effects=effects)