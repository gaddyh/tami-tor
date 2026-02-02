from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from sqlalchemy.exc import IntegrityError

from db.session import SessionLocal
from models.calendar_event import EventItem as EventRow  # SQLAlchemy model


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    if value == "":
        return None
    return datetime.fromisoformat(value)


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    if value == "":
        return None
    return date.fromisoformat(value)

def persist_event_item(
    *,
    user_id: str,
    event: EventRow,  # your Pydantic EventItem type
    raw: Optional[dict] = None,
) -> str:
    """
    Persists a Pydantic EventItem (command='create'/'update' etc.) into event_items.

    Returns the DB UUID as a string.

    Notes:
    - command is not persisted
    - item_id is tool-level; DB primary key is 'id'
    """
    if not user_id:
        raise ValueError("user_id is required")
    if not event.title:
        raise ValueError("event.title is required")

    # Determine all_day + parse appropriate fields
    all_day = bool(event.all_day)

    start_at = _parse_dt(event.datetime)
    end_at = _parse_dt(event.end_datetime)

    start_date = _parse_date(event.date)
    end_date = _parse_date(event.end_date)

    # Validate shape (match DB CHECK constraints)
    if all_day:
        if not start_date or not end_date:
            raise ValueError("all_day=True requires date and end_date")
        if start_at or end_at:
            raise ValueError("all_day=True cannot include datetime/end_datetime")
        if end_date <= start_date:
            raise ValueError("end_date must be > date")
    else:
        if not start_at or not end_at:
            raise ValueError("all_day=False requires datetime and end_datetime")
        if start_date or end_date:
            raise ValueError("all_day=False cannot include date/end_date")
        if end_at <= start_at:
            raise ValueError("end_datetime must be > datetime")

    delete_scope = getattr(event, "delete_scope", "single") or "single"
    if delete_scope not in ("single", "series", "this_and_following"):
        raise ValueError("delete_scope must be single|series|this_and_following")

    # Convert nested pydantic objects to JSONable dicts
    participants_json = (
        [p.model_dump(exclude_none=True) for p in (event.participants or [])]
        if event.participants is not None
        else None
    )
    reminders_json = (
        [r.model_dump(exclude_none=True) for r in (event.reminders or [])]
        if event.reminders is not None
        else None
    )
    recurrence_json = event.recurrence.model_dump(exclude_none=True) if event.recurrence else None

    with SessionLocal() as db:
        try:
            row = EventRow(
                user_id=user_id,
                item_type="event",

                title=event.title,
                description=event.description,
                status="open",

                op_id=getattr(event, "op_id", None),

                allow_conflicts=bool(event.allow_conflicts),

                datetime=start_at,
                end_datetime=end_at,
                start_date=start_date,
                end_date=end_date,
                all_day=all_day,

                timezone=event.timezone,
                location=event.location,

                participants=participants_json,
                recurrence=recurrence_json,
                reminders=reminders_json,

                delete_scope=delete_scope,
                send_updates=bool(getattr(event, "send_updates", False)),
                notify=bool(getattr(event, "notify", False)),

                raw=raw,
            )
            db.add(row)
            db.flush()
            db.commit()
            return str(row.id)

        except IntegrityError:
            db.rollback()

            # Optional idempotent behavior on (user_id, op_id)
            op_id = getattr(event, "op_id", None)
            if op_id:
                existing = (
                    db.query(EventRow)
                    .filter(EventRow.user_id == user_id, EventRow.op_id == op_id)
                    .one_or_none()
                )
                if existing:
                    return str(existing.id)

            raise

from __future__ import annotations

from datetime import datetime, date
from typing import Optional, Any
import uuid as uuid_lib

from sqlalchemy.exc import IntegrityError

from db.session import SessionLocal
from models.event_item import EventItem as EventRow  # SQLAlchemy model


def update_event_item(
    *,
    user_id: str,
    event,  # your Pydantic EventItem
    gcal_event_id: Optional[str] = None,
    raw: Optional[dict] = None,
) -> str:
    """
    Update an existing event_items row (single table) using a Pydantic EventItem.

    - event.item_id must be the DB UUID (string).
    - Only fields that are not None on the Pydantic object are applied.
    - gcal_event_id can be passed explicitly (common after sync with Google).
    """
    if not user_id:
        raise ValueError("user_id is required")
    if not event.item_id:
        raise ValueError("event.item_id is required for update")

    try:
        event_uuid = uuid_lib.UUID(str(event.item_id))
    except ValueError as e:
        raise ValueError("event.item_id must be a UUID string") from e

    with SessionLocal() as db:
        row: EventRow | None = (
            db.query(EventRow)
            .filter(EventRow.id == event_uuid, EventRow.user_id == user_id)
            .one_or_none()
        )
        if not row:
            raise ValueError("event not found")

        # --- apply scalar updates (only if not None) ---
        # Base-ish fields
        if event.title is not None:
            row.title = event.title
        if event.description is not None:
            row.description = event.description
        if getattr(event, "status", None) is not None:
            row.status = str(event.status)

        # Event flags
        if event.allow_conflicts is not None:
            row.allow_conflicts = bool(event.allow_conflicts)

        if event.timezone is not None:
            row.timezone = event.timezone
        if event.location is not None:
            row.location = event.location

        if getattr(event, "delete_scope", None) is not None:
            row.delete_scope = event.delete_scope

        if getattr(event, "send_updates", None) is not None:
            row.send_updates = bool(event.send_updates)

        if getattr(event, "notify", None) is not None:
            row.notify = bool(event.notify)

        # NEW field
        if gcal_event_id is not None:
            row.gcal_event_id = gcal_event_id

        # raw payload (optional)
        if raw is not None:
            row.raw = raw

        # Nested payloads
        if event.participants is not None:
            row.participants = [p.model_dump(exclude_none=True) for p in event.participants]
        if event.reminders is not None:
            row.reminders = [r.model_dump(exclude_none=True) for r in event.reminders]
        if event.recurrence is not None:
            row.recurrence = event.recurrence.model_dump(exclude_none=True)
        elif event.recurrence is None and "recurrence" in event.model_fields_set:
            # explicit recurrence=None means "clear it"
            row.recurrence = None

        # --- time fields: apply then validate final shape ---
        # Apply explicit all_day change if provided
        if getattr(event, "all_day", None) is not None:
            row.all_day = bool(event.all_day)

        # Apply explicit time/date changes if provided
        if event.datetime is not None:
            row.datetime = _parse_dt(event.datetime)
        if event.end_datetime is not None:
            row.end_datetime = _parse_dt(event.end_datetime)
        if event.date is not None:
            row.date = _parse_date(event.date)
        if event.end_date is not None:
            row.end_date = _parse_date(event.end_date)

        # If caller explicitly set one of these fields to None (clear), honor it
        # (Pydantic v2: model_fields_set tells you it was provided)
        if "datetime" in event.model_fields_set and event.datetime is None:
            row.datetime = None
        if "end_datetime" in event.model_fields_set and event.end_datetime is None:
            row.end_datetime = None
        if "date" in event.model_fields_set and event.date is None:
            row.date = None
        if "end_date" in event.model_fields_set and event.end_date is None:
            row.end_date = None

        # Validate time shape matches your DB CHECK constraints
        if row.all_day:
            if row.date is None or row.end_date is None:
                raise ValueError("all_day=True requires date and end_date")
            if row.datetime is not None or row.end_datetime is not None:
                raise ValueError("all_day=True cannot have datetime/end_datetime")
            if row.end_date <= row.date:
                raise ValueError("end_date must be > date")
        else:
            if row.datetime is None or row.end_datetime is None:
                raise ValueError("all_day=False requires datetime and end_datetime")
            if row.date is not None or row.end_date is not None:
                raise ValueError("all_day=False cannot have date/end_date")
            if row.end_datetime <= row.datetime:
                raise ValueError("end_datetime must be > datetime")

        # Validate delete_scope
        if row.delete_scope not in ("single", "series", "this_and_following"):
            raise ValueError("delete_scope must be single|series|this_and_following")

        try:
            db.add(row)
            db.commit()
            return str(row.id)
        except IntegrityError:
            db.rollback()
            raise
