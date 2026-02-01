
from models.session_state import SessionState
from handlers.models import HandlerResult
from models.session import Session
from adapters.primitivies import RawMessage
from typing import Any
from observability.obs import instrument_io

@instrument_io(
    name="client_confirm_btn_btn",
    meta={"operation": "client_confirm_btn_btn"},
    input_fn=lambda state, msg, ctx: {
        "state": state,
        "ctx": ctx,
    },
    output_fn=lambda result: result,
    redact=True
)
def client_confirm_btn_btn(state: SessionState, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    print("client_confirm_btn_btn ", state)
    return HandlerResult(state=state, effects=[])