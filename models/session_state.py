from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict


class SessionFlow(str, Enum):
    CLIENT_BOOKING = "client_booking"
    OWNER_APPROVAL = "owner_approval"


class SessionStep(str, Enum):
    OWNER_CLIENT_DETAILS = "owner_client_details"
    INIT = "init"
    SERVICE_PICK = "service_pick"
    SLOTS_PICK = "slots_pick"
    CONFIRM = "confirm"
    DONE = "done"
    CANCELLED = "cancelled"


DEFAULT_FLOW = SessionFlow.CLIENT_BOOKING
DEFAULT_STEP = SessionStep.INIT
DEFAULT_DATA: dict[str, Any] = {}
DEFAULT_VERSION = 1
