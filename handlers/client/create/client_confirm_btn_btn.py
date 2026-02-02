
from models.session_state import SessionState
from handlers.models import HandlerResult, Effect
from adapters.primitivies import RawMessage
from models.session_state import SessionFlow, SessionStep
from typing import Any
from observability.obs import instrument_io
from handlers.utility import get_btn_reply_id

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
    effects: list[Effect] = []

    btn_id = get_btn_reply_id(msg)
    if btn_id and btn_id.endswith("_confirm"):
        # On confirm: finish client flow + trigger owner flow
        state.step = SessionStep.DONE
        effects.append({"kind": "CREATE_EVENT", "to": "", "text": ""})
        effects.append({"kind": "SEND_CONFIRMATION", "to": "client", "text": "התור נקבע בהצלחה."})
        effects.append({"kind": "SEND_CONFIRMATION", "to": "owner", "payload": {"summary": state.data}})
        return HandlerResult(state=state, effects=effects)
    return HandlerResult(state=state, effects=effects)