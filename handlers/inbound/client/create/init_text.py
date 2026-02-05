from models.session_state import SessionState, SessionStep, InputType
from handlers.models import HandlerResult, Effect
from adapters.primitivies import RawMessage
from typing import Any
from observability.obs import instrument_io
from handlers.utility import build_service_rows
from agents.core import get_llm_bootstrap

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

    text = msg.content.text.strip()
    if "שלי" in text:
        effects.append({"kind": "FETCH_EVENTS", "to": "client", "rows": []})
        return HandlerResult(state=state, effects=effects)

    if text in ["שלום", "היי", "הי", "אהלן"]:
        state.step = SessionStep.SERVICE_PICK
        state.expected_type = InputType.LIST_ID
        effects.append({"kind": "SEND_SERVICE_LIST", "to": "client", "rows": build_service_rows(services)})
        return HandlerResult(state=state, effects=effects)

    if "חדש" in text:
        state.step = SessionStep.SERVICE_PICK
        state.expected_type = InputType.LIST_ID
        effects.append({"kind": "SEND_SERVICE_LIST", "to": "client", "rows": build_service_rows(services)})
        return HandlerResult(state=state, effects=effects)
    
    state.data.bootstrap = get_llm_bootstrap(text, services)
    print("bootstrap: ", state.data.bootstrap)
    if state.data.bootstrap.is_empty():
        state.step = SessionStep.SERVICE_PICK
        state.expected_type = InputType.LIST_ID
        effects.append({"kind": "SEND_SERVICE_LIST", "to": "client", "rows": build_service_rows(services)})
        return HandlerResult(state=state, effects=effects)

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
        if len(effects) == 0:
            effects.append({"kind": "SEND_SLOTS_LIST", "to": "client", "rows": []})

    if state.data.bootstrap.has_any_date_or_time():
        timezone = ctx.get("timezone") or "Asia/Jerusalem"
        state.data.bootstrap_start_dt, state.data.bootstrap_end_dt = state.data.bootstrap.to_datetimes(timezone)
        state.step = SessionStep.SLOTS_PICK
        state.expected_type = InputType.LIST_ID
        if len(effects) == 0:
            effects.append({"kind": "SEND_SLOTS_LIST", "to": "client", "rows": []})    
        
    return HandlerResult(state=state, effects=effects)