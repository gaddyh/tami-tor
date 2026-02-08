
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Literal, List
from typing import Dict, Any

# ----------------------------
# Domain
# ----------------------------

class Actor(str, Enum):
    CLIENT = "client"
    OWNER = "owner"
    PROVIDER = "provider"


class SessionStep(str, Enum):
    INIT = "init"
    SERVICE_PICK = "service_pick"
    SLOTS_PICK = "slots_pick"
    CONFIRM = "confirm"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class Service:
    id: str
    name: str
    duration_min: int


@dataclass
class Slot:
    id: str
    start_iso: str
    end_iso: str


@dataclass
class BookingParams:
    business_id: str
    client_id: str


# ----------------------------
# Inbound event (workflow-safe)
# ----------------------------

InboundKind = Literal["text", "button", "list", "audio", "media", "location", "unknown"]

@dataclass
class InboundEvent:
    event_id: str
    client_id: str
    kind: InboundKind
    text: Optional[str] = None
    list_id: Optional[str] = None
    button_id: Optional[str] = None
    media: Optional[Dict[str, Any]] = None


# ----------------------------
# Session state (single source of truth)
# ----------------------------

InboundKindSmall = Literal["text", "button", "list", "audio", "unknown"]

@dataclass
class SessionData:
    client_name: Optional[str] = None

    service_id: Optional[str] = None
    service_name: Optional[str] = None
    duration_min: Optional[int] = None

    availability_cursor: Optional[str] = None
    chosen_slot_id: Optional[str] = None

    delete_event_id: Optional[str] = None
    confirmed: Optional[bool] = None


@dataclass
class SessionState:
    actor: Actor = Actor.CLIENT
    step: SessionStep = SessionStep.INIT
    version: int = 1

    cancelled: bool = False
    error_message: Optional[str] = None

    data: SessionData = field(default_factory=SessionData)

    last_event_id: Optional[str] = None
    last_inbound_kind: Optional[InboundKindSmall] = None


# ----------------------------
# Helpers: explicit IDs
# ----------------------------

def svc_row_id(x: str) -> str:
    return f"svc:{x}"

def slot_row_id(x: str) -> str:
    return f"slot:{x}"

def parse_svc_row_id(x: Optional[str]) -> Optional[str]:
    if not x:
        return None
    return x[4:] if x.startswith("svc:") and len(x) > 4 else None

def parse_slot_row_id(x: Optional[str]) -> Optional[str]:
    if not x:
        return None
    return x[5:] if x.startswith("slot:") and len(x) > 5 else None

