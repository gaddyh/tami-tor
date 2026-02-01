
from models.session_state import SessionState
from handlers.models import HandlerResult
from models.session import Session
from adapters.primitivies import RawMessage
from typing import Any
from observability.obs import instrument_io

@instrument_io(
    name="client_show_slots_btn_text",
    meta={"operation": "client_show_slots_btn_text"},
    input_fn=lambda session, msg, ctx: {
        "work_id": str(session.session_id),
        "business_id": session.business_id or "",
        "client_id": session.client_id or "",
        "flow": session.state_json["flow"],
        "step": session.state_json["step"],
        "ctx": ctx,
    },
    output_fn=lambda result: result,
    redact=True
)
def client_show_slots_btn_text(session: Session, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    print("client_show_slots_btn_text ", session.state_json)
    return HandlerResult(state=SessionState.model_validate(session.state_json), effects=[])