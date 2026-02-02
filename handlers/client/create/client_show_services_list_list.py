
from models.session_state import SessionState, SessionStep, InputType
from handlers.models import HandlerResult, Effect
from adapters.primitivies import RawMessage
from typing import Any
from observability.obs import instrument_io
from handlers.utility import get_list_reply_id

@instrument_io(
    name="client_show_services_list_list",
    meta={"operation": "client_show_services_list_list"},
    input_fn=lambda state, msg, ctx: {
        "state": state,
        "ctx": ctx,
    },
    output_fn=lambda result: result,
    redact=True
)
def client_show_services_list_list(state: SessionState, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    print("client_show_services_list_list ", state)
    effects: list[Effect] = []
    selected_service_id = get_list_reply_id(msg)

    if not selected_service_id:
        # user sent something else while we're expecting a list selection
        effects.append({
            "kind": "SEND_TEXT",
            "to": "client",
            "text": "בחרי שירות מהרשימה בבקשה 🙂",
        })
        return HandlerResult(state=state, effects=effects)

    # validate against ctx services
    services = ctx.get("services") or []
    service = next((s for s in services if getattr(s, "id", None) == selected_service_id), None)
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
    return HandlerResult(state=state, effects=effects)