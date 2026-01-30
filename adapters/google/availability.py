from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz
from collections import defaultdict
from adapters.google.tokens import get_valid_credentials
from models.availability import TimeSlot, SlotChunk, ChunkedAvailability
def init_google_calendar(user_id: str):
    creds = get_valid_credentials(user_id)
    service = build('calendar', 'v3', credentials=creds)
    return service

def find_free_slots(busy_periods, start_dt, end_dt, timezone):
    """
    Find free time slots between busy periods.
    
    Args:
        busy_periods: List of busy time ranges from Google Calendar
        start_dt: datetime object (timezone-aware) for start of search range
        end_dt: datetime object (timezone-aware) for end of search range
        timezone: String timezone name (e.g., 'Asia/Jerusalem')
    
    Returns:
        List of free time slots as dictionaries with 'start' and 'end' datetime objects
    """
    tz = pytz.timezone(timezone)
    free_slots = []
    
    # Convert busy periods to datetime objects
    busy_times = []
    for period in busy_periods:
        busy_start = datetime.fromisoformat(period['start'].replace('Z', '+00:00')).astimezone(tz)
        busy_end = datetime.fromisoformat(period['end'].replace('Z', '+00:00')).astimezone(tz)
        busy_times.append((busy_start, busy_end))
    
    # Sort busy times by start time
    busy_times.sort(key=lambda x: x[0])
    
    # Find gaps between busy periods
    current_time = start_dt
    
    for busy_start, busy_end in busy_times:
        # If there's a gap before this busy period
        if current_time < busy_start:
            free_slots.append({
                'start': current_time,
                'end': busy_start
            })
        # Move current time to end of this busy period
        current_time = max(current_time, busy_end)
    
    # Add final slot if there's time left
    if current_time < end_dt:
        free_slots.append({
            'start': current_time,
            'end': end_dt
        })
    
    return free_slots


def split_slots_by_day(free_slots, slot_duration_minutes=60, 
                       working_hours_start="09:00", working_hours_end="17:00",
                       weekend_days=[4, 5]):  # Friday=4, Saturday=5
    """
    Split free slots by day and duration, filtering by working hours and weekdays.
    
    Args:
        free_slots: List of dicts with 'start' and 'end' datetime objects
        slot_duration_minutes: Duration of each slot in minutes (default 60)
        working_hours_start: Start of working hours in "HH:MM" format
        working_hours_end: End of working hours in "HH:MM" format
        weekend_days: List of weekday numbers to exclude (0=Monday, 6=Sunday)
    """
    slots_by_day = defaultdict(list)
    slot_duration = timedelta(minutes=slot_duration_minutes)
    
    # Parse working hours
    work_start_time = datetime.strptime(working_hours_start, "%H:%M").time()
    work_end_time = datetime.strptime(working_hours_end, "%H:%M").time()
    
    for slot in free_slots:
        # Extract start and end from dictionary
        start = slot['start']
        end = slot['end']
        
        current = start
        
        while current < end:
            # Skip weekend days
            if current.weekday() in weekend_days:
                current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                continue
            
            # Get working hours boundaries for this day
            day_work_start = current.replace(
                hour=work_start_time.hour, 
                minute=work_start_time.minute, 
                second=0, 
                microsecond=0
            )
            day_work_end = current.replace(
                hour=work_end_time.hour, 
                minute=work_end_time.minute, 
                second=0, 
                microsecond=0
            )
            
            # Adjust current to start of working hours if before
            if current < day_work_start:
                current = day_work_start
            
            # The segment ends at working hours end, day end, or actual end
            segment_end = min(day_work_end, end)
            
            # Skip if we're past working hours for this day
            if current >= day_work_end:
                current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                continue
            
            # Split this segment into fixed-duration slots
            slot_start = current
            while slot_start + slot_duration <= segment_end:
                slot_end = slot_start + slot_duration
                day_key = slot_start.date()
                slots_by_day[day_key].append((slot_start, slot_end))
                slot_start = slot_end
            
            # Move to the start of the next day
            current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    return dict(sorted(slots_by_day.items()))

from collections import OrderedDict

def limit_slots_by_day(slots_by_day: dict, limit: int = 8) -> dict:
    """
    Keep only the first `limit` slots globally (chronological) while preserving day grouping.
    slots_by_day: {date: [(start_dt, end_dt), ...]}
    """
    if limit is None or limit <= 0:
        return {}

    remaining = limit
    limited = OrderedDict()

    for day, slots in slots_by_day.items():
        if remaining <= 0:
            break

        take = slots[:remaining]
        if take:
            limited[day] = take
            remaining -= len(take)

    return dict(limited)

def format_slots_for_llm(slots_by_day):
    """Format slots in a clean structure for LLM consumption."""
    formatted = []
    
    for day, slots in slots_by_day.items():
        day_data = {
            "date": day.isoformat(),
            "day_name": day.strftime('%A'),
            "slots": []
        }
        
        for start, end in slots:
            duration = end - start
            day_data["slots"].append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "start_time": start.strftime('%H:%M'),
                "end_time": end.strftime('%H:%M'),
                "duration_hours": round(duration.total_seconds() / 3600, 1)
            })
        
        formatted.append(day_data)
    
    return formatted
def get_available_slots(user_id: str, timezone: str, start_date: str = None, end_date: str = None, duration: int = 60):
    service = init_google_calendar(user_id)
    tz = pytz.timezone(timezone)
    
    # Get current time in user's timezone
    now = datetime.now(tz)
    
    if not start_date:
        start_date = now.isoformat()
    if not end_date:
        end_date = (now + timedelta(days=7)).isoformat()

    # Parse the dates and ensure they're timezone-aware
    if len(start_date) == 10:  # Just a date, no time
        start_dt = tz.localize(datetime.strptime(start_date, "%Y-%m-%d").replace(hour=9, minute=0, second=0))
    else:
        # Parse ISO format string to datetime
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        # Convert to user's timezone if not already
        if start_dt.tzinfo is None:
            start_dt = tz.localize(start_dt)
        else:
            start_dt = start_dt.astimezone(tz)
    
    if len(end_date) == 10:  # Just a date, no time
        end_dt = tz.localize(datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
    else:
        # Parse ISO format string to datetime
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        # Convert to user's timezone if not already
        if end_dt.tzinfo is None:
            end_dt = tz.localize(end_dt)
        else:
            end_dt = end_dt.astimezone(tz)

    body = {
        "items": [{"id": "primary"}],
        "timeMin": start_dt.isoformat(),
        "timeMax": end_dt.isoformat(),
        "timeZone": timezone,
    }

    print("Request body:", body)

    try:
        freebusy_result = service.freebusy().query(body=body).execute()
    except Exception as e:
        print("Error getting freebusy result", e)
        return []

    busy_periods = freebusy_result['calendars']['primary']['busy']
    print(f"Found {len(busy_periods)} busy periods:", busy_periods)
    
    # Pass datetime objects instead of strings to find_free_slots
    free_slots = find_free_slots(busy_periods, start_dt, end_dt, timezone)
    print(f"Found {len(free_slots)} free slots:", free_slots)
    
    slots_by_day = split_slots_by_day(free_slots, duration)
    #slots_by_day = limit_slots_by_day(slots_by_day)
    print(f"Slots by day: {len(slots_by_day)} days")
    
    return format_slots_for_llm(slots_by_day)

def divide_slots_into_chunks(availability_data, chunk_size=8):
    """
    Divide availability slots into chunks of specified size across all days.
    
    Args:
        availability_data: List of day objects with slots
        chunk_size: Number of slots per chunk (default: 8)
    
    Returns:
        List of chunks, each containing slots from one or more days
    """
    # Flatten all slots from all days into a single list
    all_slots = []
    for day in availability_data:
        for slot in day.get('slots', []):
            # Add day information to each slot
            slot_with_day = slot.copy()
            slot_with_day['date'] = day['date']
            slot_with_day['day_name'] = day['day_name']
            all_slots.append(slot_with_day)
    
    # Divide into chunks of 8
    chunks = []
    for i in range(0, len(all_slots), chunk_size):
        chunk = all_slots[i:i + chunk_size]
        chunks.append({
            'chunk_number': len(chunks) + 1,
            'total_slots': len(chunk),
            'slots': chunk
        })
    
    return chunks


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

if __name__ == "__main__":
    availability_data = get_available_slots("972546610655", "Asia/Jerusalem", "2026-01-15", "2026-01-20")
    chunks = divide_slots_into_chunks(availability_data, chunk_size=8)

# Each chunk will have slots from potentially multiple days
    for chunk in chunks:
        print(f"Chunk {chunk['chunk_number']}: {chunk['slots']} slots")