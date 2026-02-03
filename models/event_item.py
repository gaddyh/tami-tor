from typing import Optional, List, Literal
from pydantic import BaseModel
from models.base_item import BaseActionItem

class Participant(BaseModel):
    email: Optional[str] = None # email required by Google Calendar
    name: str # participant name required by Google Calendar
    role: Optional[Literal["organizer", "attendee"]] = "attendee"
    status: Optional[Literal["accepted", "declined", "tentative", "needsAction"]] = None

class Recurrence(BaseModel):
    freq: Literal["daily", "weekly", "monthly", "yearly"]
    interval: Optional[int] = 1
    by_day: Optional[List[str]] = None
    by_month_day: Optional[List[int]] = None
    until: Optional[str] = None
    count: Optional[int] = None

class Reminder(BaseModel):
    method: Literal["popup", "email"] = "popup"
    minutes: int

from pydantic import Field

class EventItem(BaseActionItem):
    item_type: Literal["event"] = Field(
        "event",
        description="Always 'event'. Used to distinguish event items from tasks or other item types."
    )

    allow_conflicts: bool = Field(
        False,
        description="If true, create/update the event even if it overlaps existing events (override double-booking)."
    )

    start_at: Optional[str] = Field(
        None,
        description="Start time in ISO8601 with timezone, e.g. '2025-11-26T14:00:00+02:00'."
    )

    end_at: Optional[str] = Field(
        None,
        description="End time in ISO8601 with timezone. If omitted, a default duration may be assumed."
    )

    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name (e.g. 'Asia/Jerusalem'), used if times need explicit zone context."
    )

    date: Optional[str] = Field(
        None,
        description="Start date (YYYY-MM-DD) for all-day events."
    )

    end_date: Optional[str] = Field(
        None,
        description="Exclusive end date (YYYY-MM-DD) for all-day events. For a one-day event, this is start+1."
    )

    all_day: Optional[bool] = Field(
        False,
        description="If true, use date/end_date instead of datetime/end_datetime."
    )

    location: Optional[str] = Field(
        None,
        description="Human-readable location (address, room, or link)."
    )

    participants: Optional[List[Participant]] = Field(
        None,
        description="List of participants (name/email). Emails may be resolved from contacts."
    )

    recurrence: Optional[Recurrence] = Field(
        None,
        description="Recurrence rule for repeating events (daily/weekly/etc.)."
    )

    reminders: Optional[List[Reminder]] = Field(
        None,
        description="List of reminders (e.g. 30 minutes before, 1 day before)."
    )

    delete_scope: Literal["single", "series", "this_and_following"] = Field(
        "single",
        description=(
            "How deletion applies to recurring events: "
            "'single' = this instance only, "
            "'series' = entire series, "
            "'this_and_following' = this and all future instances."
        )
    )

    send_updates: Optional[bool] = Field(
        False,
        description="If true, send calendar updates/invites to participants when changes occur."
    )

    notify: Optional[bool] = Field(
        False,
        description="If true, explicitly notify participants about this change (implementation-specific)."
    )
    


from typing import Any, Dict
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ProcessedEventResult(BaseModel):
    """
    Normalized result returned by the event store after applying a create,
    update, or delete operation on an event.
    """

    index: int = Field(
        ...,
        description=(
            "Zero-based index of this operation within a batch. "
            "Always present, even when multiple events are processed together."
        ),
    )

    ok: bool = Field(
        ...,
        description=(
            "True if the event operation succeeded. "
            "False if the operation failed or produced an error."
        ),
    )

    item_id: Optional[str] = Field(
        None,
        description=(
            "The unique identifier of the event that was created or updated. "
            "For deletions, may be null. Absent if the operation failed."
        ),
    )

    error: Optional[str] = Field(
        None,
        description=(
            "Human-readable error message, present only when ok=False. "
            "Describes what went wrong during processing."
        ),
    )

    code: Optional[str] = Field(
        None,
        description=(
            "Machine-readable error code (e.g., 'slot_taken', 'not_found', "
            "'invalid_time'). Useful for planner or UI logic."
        ),
    )

    conflicts: Optional[List[Dict[str, Any]]] = Field(
        None,
        description=(
            "List of conflicting existing events when the requested event overlaps "
            "a taken slot. Structure is intentionally flexible so the backend may "
            "include any relevant fields (titles, times, IDs, metadata). "
            "Only populated if ok=False and code indicates a scheduling conflict."
        ),
    )
