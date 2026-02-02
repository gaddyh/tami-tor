from models.session_state import SessionState, SessionStep, InputType
from handlers.models import HandlerResult, Effect
from adapters.primitivies import RawMessage
from typing import Any
from observability.obs import instrument_io
from handlers.utility import build_service_rows
from agent.core import get_llm_bootstrap

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

    state.data.bootstrap = get_llm_bootstrap(msg.content.text, services)
    print("bootstrap", state.data.bootstrap)
    if state.data.bootstrap.is_empty():
        state.step = SessionStep.SERVICE_PICK
        state.expected_type = InputType.LIST_ID
        effects.append({"kind": "SEND_SERVICE_LIST", "to": "client", "rows": build_service_rows(services)})

    if state.data.bootstrap.has_service_name():
        service_id = next((s.id for s in services if s.name == state.data.bootstrap.service_name), None)
        service = next((s for s in services if getattr(s, "id", None) == service_id), None)
        if not service:
            effects.append({
                "kind": "SEND_TEXT",
                "to": "client",
                "text": "לא מצאתי את השירות הזה. נסי לבחור שוב מהרשימה.",
            })
            return HandlerResult(state=state, effects=effects)

        # persist in session data
        state.data.service_id = getattr(service, "id", None)
        state.data.service_name = getattr(service, "name", None)
        state.data.duration = getattr(service, "duration_min", None)

        state.step = SessionStep.SLOTS_PICK
        state.expected_type = InputType.LIST_ID
        effects.append({"kind": "SEND_SLOTS_LIST", "to": "client", "rows": [   ]})

    if state.data.bootstrap.has_any_date_or_time():
        state.step = SessionStep.SLOTS_PICK
        state.expected_type = InputType.LIST_ID
        effects.append({"kind": "SEND_AVAILABILITY", "to": "client", "chunked": state.data.bootstrap})
    
        
    return HandlerResult(state=state, effects=effects)