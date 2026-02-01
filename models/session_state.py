from __future__ import annotations

from enum import Enum
from typing import Any, Optional, TypedDict
from typing import Literal

from sqlalchemy.sql.coercions import expect
from pydantic import BaseModel
from models.availability import ChunkedAvailability, TimeSlot

class Actor(str, Enum):
    CLIENT = "client"
    OWNER = "owner"
    PROVIDER = "provider"

class InputType(str, Enum):
    AUDIO = "audio"
    TEXT = "text"
    BTN_ID = "btn_id"
    LIST_ID = "list_id"

class SessionFlow(str, Enum):
    CLIENT_CREATE = "client_create"
    CLIENT_UPDATE = "client_update"
    CLIENT_DELETE = "client_delete" 
    PROVIDER_APPROVAL = "provider_approval"


class SessionStep(str, Enum):
    OWNER_CLIENT_DETAILS = "owner_client_details"
    INIT = "init"
    SERVICE_PICK = "service_pick"
    SLOTS_PICK = "slots_pick"
    CONFIRM = "confirm"
    DONE = "done"
    CANCELLED = "cancelled"


DEFAULT_FLOW = SessionFlow.CLIENT_CREATE
DEFAULT_STEP = SessionStep.INIT
DEFAULT_DATA: dict[str, Any] = {}
DEFAULT_VERSION = 1

class SessionData(BaseModel):
    service_id: str
    service_name: str
    duration: int
    chunked:ChunkedAvailability
    chunked_index: int

    chosen_slot:TimeSlot

    data: dict[str, Any]

class SessionState(BaseModel):
    actor: Actor
    flow: SessionFlow
    step: SessionStep
    input_type: InputType
    expected_type: Optional[InputType]
    
    data: Optional[SessionData]