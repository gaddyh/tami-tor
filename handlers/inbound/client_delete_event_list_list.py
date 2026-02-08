
from models.session_state import SessionState, SessionStep, InputType
from handlers.models import HandlerResult, Effect, SendSlotsListEffect, SendConfirmButtonsEffect
from adapters.primitivies import RawMessage
from typing import Any
from observability.obs import instrument_io
from handlers.utility import get_list_reply_id
from handlers.inbound.helper import ListResponse, NavigationResponse, SlotSelectionResponse, DisabledActionResponse, UnknownActionResponse
from models.availability import TimeSlot
from handlers.helper import handle_list_response
@instrument_io(
    name="client_delete_event_list_list",
    meta={"operation": "client_delete_event_list_list"},
    input_fn=lambda state, msg, ctx: {
        "state": state,
        "ctx": ctx,
    },
    output_fn=lambda result: result,
    redact=True
)
def client_delete_event_list_list(state: SessionState, msg: RawMessage, ctx: dict[str, Any]) -> HandlerResult:
    print("client_delete_event_list_list ", state)
    effects: list[Effect] = []
    list_id = get_list_reply_id(msg)
    rows = state.data.delete_event_list or []
    row = next((row for row in rows if row["id"] == list_id), None)
    # effect: delete event, send delete confirmation
    effects.append({"kind": "DELETE_EVENT", "to": "api", "event_id": row["id"]})
    effects.append({"kind": "SEND_DELETE_CONFIRMATION", "to": "client", "text": "האירוע נמחק בהצלחה."})

    
