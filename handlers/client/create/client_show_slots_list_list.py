
from models.session_state import SessionState
from handlers.models import HandlerResult
from adapters.primitivies import RawMessage
from typing import Any
from observability.obs import instrument_io

@instrument_io(
    name="client_show_slots_list_list",
    meta={"operation": "client_show_slots_list_list"},
    input_fn=lambda state, msg, ctx: {
        "state": state,
        "ctx": ctx,
    },
    output_fn=lambda result: result,
    redact=True
)
def client_show_slots_list_list(state: SessionState, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    print("client_show_slots_list_list ", state)
    return HandlerResult(state=state, effects=[])