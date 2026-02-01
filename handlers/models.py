from dataclasses import dataclass
from handlers.utility import build_service_rows, get_list_reply_id, get_btn_reply_id
from models.session_state import SessionFlow, SessionStep
from adapters.primitivies import RawMessage
from typing import Any, Literal, TypedDict, Union
from reducers.helper import handle_list_response, ListResponse, NavigationResponse, SlotSelectionResponse, DisabledActionResponse, UnknownActionResponse
from models.availability import ChunkedAvailability, TimeSlot
class ListRow(TypedDict):
    id: str          # payload you get back in list_reply.id
    title: str
    description: str | None


from typing import Any, Literal, TypedDict

class SendServiceListEffect(TypedDict):
    kind: Literal["SEND_SERVICE_LIST"]
    to: Literal["client"]
    rows: list[dict[str, Any]]  # rows = [{"id": "...", "title": "..."}]

class SendSlotsListEffect(TypedDict):
    kind: Literal["SEND_SLOTS_LIST"]
    to: Literal["client"]
    rows: list[dict[str, Any]]

class SendConfirmButtonsEffect(TypedDict):
    kind: Literal["SEND_CONFIRM_BUTTONS"]
    to: Literal["client"]
    body: str
    buttons: list[dict[str, str]]  # [{"id":"yes","title":"כן"}, ...]

class SendTextEffect(TypedDict):
    kind: Literal["SEND_TEXT"]
    to: Literal["client", "owner"]
    text: str

class EnqueueOwnerApprovalEffect(TypedDict):
    kind: Literal["ENQUEUE_OWNER_APPROVAL"]
    # keep it minimal: reducer emits *intent*, handler fills DB ids
    payload: dict[str, Any]

Effect = Union[SendTextEffect, EnqueueOwnerApprovalEffect, SendConfirmButtonsEffect, SendServiceListEffect, SendSlotsListEffect]

@dataclass(frozen=True)
class ReduceResult:
    flow: SessionFlow
    step: SessionStep
    data: dict[str, Any]
    effects: list[Effect]
