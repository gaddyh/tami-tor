from __future__ import annotations

from datetime import datetime, date
from typing import Optional, Any, Mapping
from uuid import UUID
from enum import Enum

from sqlalchemy.exc import IntegrityError

from db.session import SessionLocal
from models.calendar_event import EventRow  # your ORM class


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


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value)


def persist_event_item(
    *,
    user_id: str,
    event,  # <-- Pydantic EventItem (NOT EventRow)
    raw: Optional[dict] = None,
) -> str:
    if not user_id:
        raise ValueError("user_id is required")
    if not event.title:
        raise ValueError("event.title is required")

    all_day = bool(getattr(event, "all_day", False))

    start_at = _parse_dt(getattr(event, "start_at", None))
    end_at = _parse_dt(getattr(event, "end_at", None))
    start_date = _parse_date(getattr(event, "date", None))
    end_date = _parse_date(getattr(event, "end_date", None))

    # Validate shape (matches your DB CHECK constraints)
    if all_day:
        if not start_date or not end_date:
            raise ValueError("all_day=True requires date and end_date")
        if start_at or end_at:
            raise ValueError("all_day=True cannot include start_at/end_at")
        if end_date <= start_date:
            raise ValueError("end_date must be > date")
    else:
        if not start_at or not end_at:
            raise ValueError("all_day=False requires start_at and end_at")
        if start_date or end_date:
            raise ValueError("all_day=False cannot include date/end_date")
        if end_at <= start_at:
            raise ValueError("end_at must be > start_at")

    delete_scope = getattr(event, "delete_scope", "single") or "single"
    if delete_scope not in ("single", "series", "this_and_following"):
        raise ValueError("delete_scope must be single|series|this_and_following")

    # ---- JSONB payloads (ALWAYS jsonify) ----
    participants_json = None
    if getattr(event, "participants", None) is not None:
        participants_json = jsonify(
            [p.model_dump(mode="json", exclude_none=True) for p in (event.participants or [])]
        )

    reminders_json = None
    if getattr(event, "reminders", None) is not None:
        reminders_json = jsonify(
            [r.model_dump(mode="json", exclude_none=True) for r in (event.reminders or [])]
        )

    recurrence_json = None
    if getattr(event, "recurrence", None):
        recurrence_json = jsonify(event.recurrence.model_dump(mode="json", exclude_none=True))

    with SessionLocal() as db:
        try:
            row = EventRow(
                user_id=user_id,
                op_id=getattr(event, "op_id", None),
                item_type="event",

                title=event.title,
                description=getattr(event, "description", None),
                status=str(getattr(event, "status", "open")),

                gcal_event_id=getattr(event, "gcal_event_id", None),

                allow_conflicts=bool(getattr(event, "allow_conflicts", False)),

                # ✅ correct ORM column names
                start_at=start_at,
                end_at=end_at,
                date=start_date,
                end_date=end_date,
                all_day=all_day,

                timezone=getattr(event, "timezone", None),
                location=getattr(event, "location", None),

                participants=participants_json,
                recurrence=recurrence_json,
                reminders=reminders_json,

                delete_scope=delete_scope,
                send_updates=bool(getattr(event, "send_updates", False)),
                notify=bool(getattr(event, "notify", False)),

                raw=jsonify(raw) if raw is not None else None,
            )

            db.add(row)
            db.flush()
            db.commit()
            return str(row.id)

        except IntegrityError:
            db.rollback()
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




def update_event_item(
    *,
    user_id: str,
    event: EventRow,  # your Pydantic EventItem
    gcal_event_id: Optional[str] = None,
    raw: Optional[dict] = None,
) -> str:
    """
    Update an existing event_items row (single table) using a Pydantic EventItem.

    - event.id must be the DB UUID (string).
    - Only fields that are not None on the Pydantic object are applied.
    - gcal_event_id can be passed explicitly (common after sync with Google).
    """
    if not user_id:
        raise ValueError("user_id is required")
    if not event.id:
        raise ValueError("event.id is required for update")

    try:
        event_uuid = uuid_lib.UUID(str(event.id))
    except ValueError as e:
        raise ValueError("event.id must be a UUID string") from e

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
            row.raw = jsonify(raw)

        # Nested payloads
        if event.participants is not None:
            row.participants = [
                p.model_dump(mode="json", exclude_none=True)
                for p in event.participants
            ]
        if event.reminders is not None:
            row.reminders = [
                r.model_dump(mode="json", exclude_none=True)
                for r in event.reminders
            ]
        if event.recurrence is not None:
            row.recurrence = event.recurrence.model_dump(mode="json", exclude_none=True)
            
        elif event.recurrence is None and "recurrence" in event.model_fields_set:
            # explicit recurrence=None means "clear it"
            row.recurrence = None

        # --- time fields: apply then validate final shape ---
        # Apply explicit all_day change if provided
        if getattr(event, "all_day", None) is not None:
            row.all_day = bool(event.all_day)

        # Apply explicit time/date changes if provided
        if event.start_at is not None:
            row.start_at = _parse_dt(event.start_at)
        if event.end_at is not None:
            row.end_at = _parse_dt(event.end_at)
        if event.date is not None:
            row.date = _parse_date(event.date)
        if event.end_date is not None:
            row.end_date = _parse_date(event.end_date)

        # If caller explicitly set one of these fields to None (clear), honor it
        # (Pydantic v2: model_fields_set tells you it was provided)
        if "datetime" in event.model_fields_set and event.start_at is None:
            row.start_at = None
        if "end_datetime" in event.model_fields_set and event.end_at is None:
            row.end_at = None
        if "date" in event.model_fields_set and event.date is None:
            row.date = None
        if "end_date" in event.model_fields_set and event.end_date is None:
            row.end_date = None

        # Validate time shape matches your DB CHECK constraints
        if row.all_day:
            if row.date is None or row.end_date is None:
                raise ValueError("all_day=True requires date and end_date")
            if row.start_at is not None or row.end_at is not None:
                raise ValueError("all_day=True cannot have datetime/end_datetime")
            if row.end_date <= row.date:
                raise ValueError("end_date must be > date")
        else:
            if row.start_at is None or row.end_at is None:
                raise ValueError("all_day=False requires datetime and end_datetime")
            if row.date is not None or row.end_date is not None:
                raise ValueError("all_day=False cannot have date/end_date")
            if row.end_at <= row.start_at:
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
