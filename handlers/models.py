from dataclasses import dataclass
from handlers.utility import build_service_rows, get_list_reply_id, get_btn_reply_id
from adapters.primitivies import RawMessage
from typing import Any, Literal, TypedDict, Union
from reducers.helper import handle_list_response, ListResponse, NavigationResponse, SlotSelectionResponse, DisabledActionResponse, UnknownActionResponse
from models.availability import ChunkedAvailability, TimeSlot
from typing import Callable, Dict, Any, Optional, Tuple

from models.session_state import Actor, InputType, SessionFlow, SessionStep, SessionState
from models.session import Session

from adapters.primitivies import RawMessage
from pydantic import BaseModel

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

class Effect(TypedDict):
    kind: str  
    to: Literal["client", "owner", "api"]
    text: Optional[str] = None
    payload: Optional[dict[str, Any]] = None

@dataclass(frozen=True)
class ReduceResult:
    flow: SessionFlow
    step: SessionStep
    data: dict[str, Any]
    effects: list[Effect]

class HandlerResult(BaseModel):
    state: SessionState
    effects: list[Effect]


Handler = Callable[[Session, RawMessage, dict[str, Any]], HandlerResult]

# (flow, step, input_type, expected_type) where expected_type=None means "wildcard"
RouteKey = Tuple[Actor, SessionFlow, SessionStep, InputType, Optional[InputType]]

INBOUND_REGISTRY: Dict[RouteKey, Handler] = {}


class NoRouteFound(Exception):
    pass

