from __future__ import annotations

from enum import Enum
from typing import Any, Optional, TypedDict
from typing import Literal

from pydantic import BaseModel
from models.availability import ChunkedAvailability, TimeSlot
from agents.core import CalendarEventBootstrap
from datetime import datetime
 
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
    PROVIDER = "provider"


class SessionStep(str, Enum):
    ROUTE = "route"
    OWNER_CLIENT_DETAILS = "owner_client_details"
    INIT = "init"
    SERVICE_PICK = "service_pick"
    SLOTS_PICK = "slots_pick"
    CLIENT_DELETE_PICK = "client_delete_pick"
    CONFIRM = "confirm"
    DONE = "done"
    CANCELLED = "cancelled"

 
DEFAULT_FLOW = SessionFlow.CLIENT_CREATE
DEFAULT_STEP = SessionStep.ROUTE
DEFAULT_VERSION = 1

class SessionData(BaseModel):
    last_text_input: Optional[str] = None

    bootstrap_start_dt: Optional[datetime] = None
    bootstrap_end_dt: Optional[datetime] = None
    
    client_name: Optional[str] = None
    
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    duration: Optional[int] = None
    
    chunked:Optional[ChunkedAvailability] = None
    chunked_index: Optional[int] = None
    bootstrap: Optional[CalendarEventBootstrap] = None
    chosen_slot:Optional[TimeSlot] = None
    chosen_slot_id: Optional[str] = None

    confirmed: Optional[bool] = None
    booking_id: Optional[str] = None
   


class SessionState(BaseModel):
    actor: Actor = Actor.CLIENT
    flow: SessionFlow = SessionFlow.CLIENT_CREATE
    step: SessionStep = SessionStep.ROUTE
    input_type: InputType = InputType.TEXT
    error_message: Optional[str] = None
    data: SessionData = SessionData()
    expected_type: Optional[InputType] = None
    last_event_id: Optional[str] = None
    cancelled: bool = False

