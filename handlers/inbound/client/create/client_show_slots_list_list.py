
from models.session_state import SessionState, SessionStep, InputType
from handlers.models import HandlerResult, Effect, SendSlotsListEffect, SendConfirmButtonsEffect
from adapters.primitivies import RawMessage
from typing import Any
from observability.obs import instrument_io
from handlers.utility import get_list_reply_id
from handlers.inbound.client.create.helper import handle_list_response, ListResponse, NavigationResponse, SlotSelectionResponse, DisabledActionResponse, UnknownActionResponse
from models.availability import ChunkedAvailability, TimeSlot

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
    effects: list[Effect] = []
    list_id = get_list_reply_id(msg)
    res: ListResponse = handle_list_response(list_id, state.data.chunked)
    match res:
        case NavigationResponse():
            state.data.chunked_index = res.chunk_index
            state.step = SessionStep.SLOTS_PICK
            state.error_message = None
            effects.append(SendSlotsListEffect(kind="SEND_SLOTS_LIST", to="client", rows=[]))
            return HandlerResult(state=state, effects=effects)

        case SlotSelectionResponse():
            slot: TimeSlot = res.slot
            state.data.chosen_slot = slot
            state.step = SessionStep.CONFIRM
            state.error_message = None
            state.expected_type = InputType.BTN_ID
            effects.append( SendConfirmButtonsEffect(kind="SEND_CONFIRM_BUTTONS", to="client", body="", buttons=[]))
            return HandlerResult(state=state, effects=effects)

        case DisabledActionResponse():
            state.step = SessionStep.SLOTS_PICK
            state.error_message = res.message
            return HandlerResult(state=state, effects=effects)

        case UnknownActionResponse():
            state.step = SessionStep.SLOTS_PICK
            state.error_message = res.message
            return HandlerResult(state=state, effects=effects)