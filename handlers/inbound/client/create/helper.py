
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any
from enum import Enum
from models.availability import TimeSlot

class ActionType(str, Enum):
    """Types of actions from user selection"""
    NAVIGATE = "navigate"
    SLOT_SELECTED = "slot_selected"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class NavigationDirection(str, Enum):
    """Navigation directions"""
    BACK = "back"
    NEXT = "next"


class NavigationResponse(BaseModel):
    """Response for navigation actions"""
    action: Literal[ActionType.NAVIGATE]
    direction: NavigationDirection
    chunk_index: int = Field(..., ge=0)
    message: Dict[str, Any] = Field(..., description="WhatsApp message payload")


class SlotSelectionResponse(BaseModel):
    """Response for slot selection"""
    action: Literal[ActionType.SLOT_SELECTED]
    slot: TimeSlot
    message: str = Field(..., description="Confirmation message")


class DisabledActionResponse(BaseModel):
    """Response for disabled actions"""
    action: Literal[ActionType.DISABLED]
    message: str


class UnknownActionResponse(BaseModel):
    """Response for unknown actions"""
    action: Literal[ActionType.UNKNOWN]
    message: str


# Union type for all possible responses
ListResponse = NavigationResponse | SlotSelectionResponse | DisabledActionResponse | UnknownActionResponse

