
from models.session_state import SessionState
from handlers.registry import HandlerResult
from models.session import Session
from adapters.primitivies import RawMessage
from typing import Any

def init_text(session: Session, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    print("init_text ", session.state_json)
    return HandlerResult(state=SessionState.model_validate(session.state_json), effects=[])