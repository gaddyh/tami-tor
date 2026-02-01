
from models.session_state import SessionState
from handlers.registry import HandlerResult
from models.session import Session
from adapters.primitivies import RawMessage
from typing import Any

def init_text(session: Session, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    return HandlerResult(state=SessionState.model_validate(session.state_json), effects=[])