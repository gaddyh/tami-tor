
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any
from enum import Enum
from models.availability import TimeSlot
from models.availability import ChunkedAvailability
from handlers.helper import create_whatsapp_list_message

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


def handle_list_response(
    user_selection: str, 
    chunked_availability: dict[str, Any]
) -> ListResponse:
    """
    Handle user's selection from the list message.
    
    Args:
        user_selection: The 'id' of the selected row from WhatsApp callback
        chunked_availability: ChunkedAvailability Pydantic model
    
    Returns:
        ListResponse (one of the response types)
    """
    chunked_availability = ChunkedAvailability.model_validate(chunked_availability)

    # Navigation handling - Go Back
    if user_selection.startswith("nav_back_"):
        if user_selection == "nav_back_disabled":
            return DisabledActionResponse(
                action=ActionType.DISABLED,
                message="You're already on the first page"
            )
        
        # Extract chunk index from nav_back_{chunk_index}
        chunk_index = int(user_selection.split("_")[2])
        prev_chunk = chunk_index - 1
        
        return NavigationResponse(
            action=ActionType.NAVIGATE,
            direction=NavigationDirection.BACK,
            chunk_index=prev_chunk,
            message=create_whatsapp_list_message(chunked_availability, prev_chunk)
        )
    
    # Navigation handling - Next
    elif user_selection.startswith("nav_next_"):
        # Extract chunk index from nav_next_{chunk_index}
        chunk_index = int(user_selection.split("_")[2])
        next_chunk = chunk_index + 1
        
        return NavigationResponse(
            action=ActionType.NAVIGATE,
            direction=NavigationDirection.NEXT,
            chunk_index=next_chunk,
            message=create_whatsapp_list_message(chunked_availability, next_chunk)
        )
    
    # Slot selection handling
    elif user_selection.startswith("slot_"):
        # Parse slot_{chunk_index}_{date}_{slot_index}
        parts = user_selection.split("_")
        chunk_idx = int(parts[1])
        date = parts[2]
        slot_idx = int(parts[3])
        
        # Find the actual slot
        chunk = chunked_availability.chunks[chunk_idx]
        selected_slot = None
        
        current_idx = 0
        for slot in chunk.slots:
            if slot.date == date:
                if current_idx == slot_idx:
                    selected_slot = slot
                    break
                current_idx += 1
        
        if selected_slot is None:
            return UnknownActionResponse(
                action=ActionType.UNKNOWN,
                message="Slot not found"
            )
        
        return SlotSelectionResponse(
            action=ActionType.SLOT_SELECTED,
            slot=selected_slot,
            message=f"You selected: {selected_slot.day_name}, {selected_slot.date} at {selected_slot.start_time}-{selected_slot.end_time}"
        )
    
    return UnknownActionResponse(
        action=ActionType.UNKNOWN,
        message="Unknown selection"
    )

