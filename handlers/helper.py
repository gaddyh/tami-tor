
from models.availability import ChunkedAvailability, SlotChunk, TimeSlot
from typing import List, Optional, Any
from datetime import datetime, date
from uuid import UUID
from enum import Enum
from collections.abc import Mapping
from handlers.inbound.client.create.helper import handle_list_response, ListResponse, NavigationResponse, SlotSelectionResponse, DisabledActionResponse, UnknownActionResponse, create_whatsapp_list_message, ActionType, NavigationDirection 

# Updated function to return Pydantic models
def divide_slots_into_chunks(availability_data, chunk_size=8) -> ChunkedAvailability:
    """
    Divide availability slots into chunks of specified size across all days.
    
    Args:
        availability_data: List of day objects with slots
        chunk_size: Number of slots per chunk (default: 8)
    
    Returns:
        ChunkedAvailability object with all chunks
    """
    # Flatten all slots from all days into a single list
    all_slots = []
    for day in availability_data:
        day_date = day.get("date")
        day_name_en = day.get("day_name")  # expected English name

        # Always resolve to Hebrew, always fallback to empty string (never None)
        day_name_he = _HE_DAY_MAP.get(day_name_en, "")

        for slot in day.get("slots", []):
            slot_with_day = slot.copy()
            slot_with_day["date"] = day_date
            slot_with_day["day_name"] = day_name_he  # ← ALWAYS STRING
            all_slots.append(slot_with_day)

    
    # Divide into chunks of 8
    chunks = []
    for i in range(0, len(all_slots), chunk_size):
        chunk_slots = all_slots[i:i + chunk_size]
        
        # Create TimeSlot objects
        time_slots = [TimeSlot(**slot) for slot in chunk_slots]
        
        chunks.append(SlotChunk(
            chunk_number=len(chunks) + 1,
            total_slots=len(chunk_slots),
            slots=time_slots
        ))
    
    return ChunkedAvailability(
        total_chunks=len(chunks),
        total_slots=len(all_slots),
        chunks=chunks
    )

def create_whatsapp_list_message(chunked_availability: ChunkedAvailability, to_phone: str, chunk_index: int = 0):
    """
    Create WhatsApp List Message format for availability slots with pagination.
    
    Args:
        chunked_availability: ChunkedAvailability Pydantic model
        chunk_index: Which chunk to display (0-based index)
    
    Returns:
        Dictionary formatted for WhatsApp Cloud API List Message
    """
    if chunk_index >= chunked_availability.total_chunks:
        return None
    
    chunk = chunked_availability.chunks[chunk_index]
    slots:List[TimeSlot] = chunk.slots
    
    # Group slots by date
    slots_by_date = {}
    for slot in slots:
        date = slot.date
        if date not in slots_by_date:
            slots_by_date[date] = {
                'day_name': slot.day_name, 
                'slots': []
            }
        slots_by_date[date]['slots'].append(slot)
    
    # Create sections for each day
    sections = []
    
    # Add slots sections
    for date in sorted(slots_by_date.keys()):
        day_info = slots_by_date[date]
        rows = []
        
        for i, slot in enumerate(day_info['slots']):
            slot_id = f"slot_{chunk_index}_{date}_{i}"
            slot:TimeSlot = slot
            rows.append({
                "id": slot_id,
                "title": f"{slot.start_time} - {slot.end_time}"
            })
        
        sections.append({
            "title": f"{day_info['day_name']}, {date}",
            "rows": rows
        })
    
    # Add navigation section
    navigation_rows = []
    
    # Go Back button
    if chunk_index > 0:
        navigation_rows.append({
            "id": f"nav_back_{chunk_index}",
            "title": "⬅️ תאריכים קודמים",
            "description": f"לעמוד {chunk_index}"
        })
    else:
        # Disabled "Go Back" for first chunk
        navigation_rows.append({
            "id": f"nav_back_disabled",
            "title": "⬅️ תאריכים קודמים",
            "description": "אין תאריכים קודמים"
        })
    
    # More Dates button
    if chunk_index < chunked_availability.total_chunks - 1:
        navigation_rows.append({
            "id": f"nav_next_{chunk_index}",
            "title": "⬅️ תאריכים נוספים",
            "description": f"לעמוד {chunk_index + 2}"
        })
    
    sections.append({
        "title": "Navigation",
        "rows": navigation_rows
    })
    
    # Create the full message
    message = {
            "type": "list",
            "header": {
                "type": "text",
                "text": "📅 זמנים פנויים"
            },
            "body": {
                "text": f"בחר את הזמן המועדף עליך\n\nמציג דף {chunk_index + 1} מתוך {chunked_availability.total_chunks}"
            },
            "action": {
                "button": "צפה במנים פנויים",
                "sections": sections
            }
    }
    
    return message

# Usage example with type safety
def process_user_selection(user_selection: str, chunked_availability: ChunkedAvailability):
    """Example of how to use the response handler with type checking"""
    response = handle_list_response(user_selection, chunked_availability)
    
    # Type-safe handling using match (Python 3.10+)
    match response.action:
        case ActionType.NAVIGATE:
            # TypeScript-style narrowing - response is now NavigationResponse
            print(f"Navigating {response.direction} to chunk {response.chunk_index}")
            return response.message
        
        case ActionType.SLOT_SELECTED:
            # response is now SlotSelectionResponse
            print(f"Slot selected: {response.slot.date} at {response.slot.start_time}")
            # Process booking with response.slot
            return response.message
        
        case ActionType.DISABLED:
            # response is now DisabledActionResponse
            print(f"Disabled action: {response.message}")
            return None
        
        case ActionType.UNKNOWN:
            # response is now UnknownActionResponse
            print(f"Unknown action: {response.message}")
            return None


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


def handle_whatsapp_webhook(
    webhook_data: dict, 
    chunked_availability: ChunkedAvailability, 
    access_token: str, 
    phone_number_id: str
) -> Optional[TimeSlot]:
    """
    Handle incoming webhook from WhatsApp when user makes a selection.
    
    Args:
        webhook_data: The webhook payload from WhatsApp
        chunked_availability: ChunkedAvailability Pydantic model
        access_token: WhatsApp API access token
        phone_number_id: Your WhatsApp Business phone number ID
    
    Returns:
        TimeSlot if user selected a slot, None otherwise
    """
    import requests
    
    try:
        # Extract the user's selection
        message = webhook_data['entry'][0]['changes'][0]['value']['messages'][0]
        user_phone = message['from']
        
        if message['type'] == 'interactive':
            if message['interactive']['type'] == 'list_reply':
                selected_id = message['interactive']['list_reply']['id']
                
                # Handle the selection with type-safe response
                response = handle_list_response(selected_id, chunked_availability)
                
                API_URL = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                if isinstance(response, NavigationResponse):
                    # Send the new page
                    new_message = response.message
                    new_message['to'] = user_phone
                    requests.post(API_URL, headers=headers, json=new_message)
                
                elif isinstance(response, SlotSelectionResponse):
                    # Send confirmation message
                    confirmation = {
                        "messaging_product": "whatsapp",
                        "to": user_phone,
                        "type": "text",
                        "text": {
                            "body": response.message
                        }
                    }
                    requests.post(API_URL, headers=headers, json=confirmation)
                    
                    # Return the selected slot for booking
                    return response.slot
                
                elif isinstance(response, DisabledActionResponse):
                    # Optionally send a message that this action is disabled
                    pass
    
    except Exception as e:
        print(f"Error handling webhook: {e}")
    
    return None


def jsonify(x: Any) -> Any:
    if x is None or isinstance(x, (str, int, float, bool)):
        return x
    if isinstance(x, (datetime, date)):
        return x.isoformat()
    if isinstance(x, UUID):
        return str(x)
    if isinstance(x, Enum):
        return x.value
    if isinstance(x, Mapping):
        return {str(k): jsonify(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [jsonify(v) for v in x]
    return str(x)


# Usage example:
if __name__ == "__main__":
    # Your availability data
    availability_data = _get_available_slots("972546610653", "Asia/Jerusalem", "2026-01-15", "2026-01-20")
    
    # Create chunked availability
    chunked = divide_slots_into_chunks(availability_data)
    
    # Access as Pydantic models
    print(f"Total chunks: {chunked.total_chunks}")
    print(f"Total slots: {chunked.total_slots}")
    
    # Access first chunk
    first_chunk = chunked.chunks[0]
    print(f"Chunk {first_chunk.chunk_number} has {first_chunk.total_slots} slots")
    
    # Access first slot in first chunk
    first_slot = first_chunk.slots[0]
    print(f"First slot: {first_slot.date} at {first_slot.start_time}")
    
    # Convert to JSON
    print(chunked.model_dump_json(indent=2))
    
    # Validate data
    try:
        validated = ChunkedAvailability.model_validate(chunked.model_dump())
        print("Data is valid!")
    except Exception as e:
        print(f"Validation error: {e}")

from datetime import datetime

_HE_DAY_MAP = {
    "Sunday": "יום ראשון",
    "Monday": "יום שני",
    "Tuesday": "יום שלישי",
    "Wednesday": "יום רביעי",
    "Thursday": "יום חמישי",
    "Friday": "יום שישי",
    "Saturday": "שבת",
}

def build_hebrew_slot_confirmation(slot) -> str:
    """
    Build a Hebrew confirmation message for a chosen appointment slot.

    Expects `slot` to have:
      - date: "YYYY-MM-DD"
      - day_name: e.g. "Thursday" (optional; will be mapped if present)
      - start_time: "HH:MM"
      - end_time: "HH:MM"
      - duration_hours: float
    """
    # Date formatting: 2026-01-15 -> 15/01/2026
    date_str = slot.date
    try:
        dt = datetime.strptime(slot.date, "%Y-%m-%d")
        date_str = dt.strftime("%d/%m/%Y")
    except Exception:
        pass  # keep original if parsing fails

    he_day = _HE_DAY_MAP.get(getattr(slot, "day_name", "") or "", None)

    # Duration formatting: 1.0 -> "שעה", 1.5 -> "1.5 שעות", 2.0 -> "2 שעות"
    dur = getattr(slot, "duration_hours", None)
    if isinstance(dur, (int, float)):
        if abs(dur - 1.0) < 1e-9:
            dur_str = "שעה"
        else:
            # avoid trailing .0
            dur_num = int(dur) if float(dur).is_integer() else dur
            dur_str = f"{dur_num} שעות"
    else:
        dur_str = ""

    day_part = f"{he_day}, " if he_day else ""
    dur_part = f" ({dur_str})" if dur_str else ""

    return (
        "רק לוודא 🙂\n"
        f"לקבוע תור ל-{day_part}{date_str}\n"
        f"בין {slot.start_time} ל-{slot.end_time}{dur_part}?\n\n"
    )
