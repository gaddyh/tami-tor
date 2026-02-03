# db/persist_event.py
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, date
from enum import Enum
from typing import Any, Mapping, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from db.session import SessionLocal
from models.calendar_event import EventRow  # ORM row (DB model)


def jsonify(x: Any) -> Any:
    """Convert arbitrary Python/Pydantic objects into JSON-serializable primitives."""
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


def _to_dt(v: Any) -> Optional[datetime]:
    """Accept datetime or ISO string (or None) -> datetime|None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and v:
        return datetime.fromisoformat(v)
    return None


def _to_date(v: Any) -> Optional[date]:
    """Accept date or ISO string (or None) -> date|None."""
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, str) and v:
        return date.fromisoformat(v)
    return None


def _fields_set(obj: Any) -> set[str]:
    """
    Pydantic v2: model_fields_set
    Pydantic v1: __fields_set__
    Fallback: empty set
    """
    s = getattr(obj, "model_fields_set", None)
    if isinstance(s, set):
        return s
    s = getattr(obj, "__fields_set__", None)
    if isinstance(s, set):
        return s
    return set()


def persist_event_item(
    *,
    user_id: str,
    event: Any,  # Pydantic EventItem (not ORM)
    raw: Optional[dict] = None,
) -> str:
    if not user_id:
        raise ValueError("user_id is required")
    if not getattr(event, "title", None):
        raise ValueError("event.title is required")

    all_day = bool(getattr(event, "all_day", False))

    # Accept both naming schemes:
    # - start_at / end_at (strings or datetimes)
    # - datetime / end_datetime (strings or datetimes)
    start_at = _to_dt(getattr(event, "start_at", None) or getattr(event, "datetime", None))
    end_at = _to_dt(getattr(event, "end_at", None) or getattr(event, "end_datetime", None))

    # All-day date fields (strings or dates)
    start_date = _to_date(getattr(event, "date", None))
    end_date = _to_date(getattr(event, "end_date", None))

    # Validate shape (should match DB constraints)
    if all_day:
        if not start_date or not end_date:
            raise ValueError("all_day=True requires date and end_date")
        if start_at or end_at:
            raise ValueError("all_day=True cannot include start_at/end_at (or datetime/end_datetime)")
        if end_date <= start_date:
            raise ValueError("end_date must be > date")
    else:
        if not start_at or not end_at:
            raise ValueError("all_day=False requires start_at/end_at (or datetime/end_datetime)")
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
        participants = event.participants or []
        participants_json = jsonify(
            [
                (p.model_dump(mode="json", exclude_none=True) if hasattr(p, "model_dump") else jsonify(p))
                for p in participants
            ]
        )

    reminders_json = None
    if getattr(event, "reminders", None) is not None:
        reminders = event.reminders or []
        reminders_json = jsonify(
            [
                (r.model_dump(mode="json", exclude_none=True) if hasattr(r, "model_dump") else jsonify(r))
                for r in reminders
            ]
        )

    recurrence_json = None
    if getattr(event, "recurrence", None):
        rec = event.recurrence
        recurrence_json = jsonify(rec.model_dump(mode="json", exclude_none=True) if hasattr(rec, "model_dump") else rec)

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
    event: Any,  # Pydantic EventItem (not ORM)
    event_id: Optional[str] = None,  # allow passing id explicitly
    gcal_event_id: Optional[str] = None,
    raw: Optional[dict] = None,
) -> str:
    if not user_id:
        raise ValueError("user_id is required")

    # accept event.id or explicit event_id
    eid = event_id or getattr(event, "id", None) or getattr(event, "item_id", None)
    if not eid:
        raise ValueError("event.id (or event_id) is required for update")

    try:
        event_uuid = uuid_lib.UUID(str(eid))
    except ValueError as e:
        raise ValueError("event.id must be a UUID string") from e

    fields_set = _fields_set(event)

    with SessionLocal() as db:
        row: EventRow | None = (
            db.query(EventRow)
            .filter(EventRow.id == event_uuid, EventRow.user_id == user_id)
            .one_or_none()
        )
        if not row:
            raise ValueError("event not found")

        # Scalars
        if getattr(event, "title", None) is not None:
            row.title = event.title
        if getattr(event, "description", None) is not None:
            row.description = event.description
        if getattr(event, "status", None) is not None:
            row.status = str(event.status)

        if getattr(event, "allow_conflicts", None) is not None:
            row.allow_conflicts = bool(event.allow_conflicts)

        if getattr(event, "timezone", None) is not None:
            row.timezone = event.timezone
        if getattr(event, "location", None) is not None:
            row.location = event.location

        if getattr(event, "delete_scope", None) is not None:
            row.delete_scope = event.delete_scope

        if getattr(event, "send_updates", None) is not None:
            row.send_updates = bool(event.send_updates)

        if getattr(event, "notify", None) is not None:
            row.notify = bool(event.notify)

        if gcal_event_id is not None:
            row.gcal_event_id = gcal_event_id

        if raw is not None:
            row.raw = jsonify(raw)

        # Nested JSON payloads (ensure JSON-safe)
        if getattr(event, "participants", None) is not None:
            participants = event.participants or []
            row.participants = jsonify(
                [
                    (p.model_dump(mode="json", exclude_none=True) if hasattr(p, "model_dump") else jsonify(p))
                    for p in participants
                ]
            )

        if getattr(event, "reminders", None) is not None:
            reminders = event.reminders or []
            row.reminders = jsonify(
                [
                    (r.model_dump(mode="json", exclude_none=True) if hasattr(r, "model_dump") else jsonify(r))
                    for r in reminders
                ]
            )

        if getattr(event, "recurrence", None) is not None:
            rec = event.recurrence
            row.recurrence = jsonify(rec.model_dump(mode="json", exclude_none=True) if hasattr(rec, "model_dump") else rec)
        elif "recurrence" in fields_set:
            # explicit recurrence=None => clear
            row.recurrence = None

        # Time fields: accept both naming schemes
        if getattr(event, "all_day", None) is not None:
            row.all_day = bool(event.all_day)

        start_in = getattr(event, "start_at", None)
        end_in = getattr(event, "end_at", None)
        dt_in = getattr(event, "datetime", None)
        enddt_in = getattr(event, "end_datetime", None)

        if start_in is not None or dt_in is not None:
            row.start_at = _to_dt(start_in or dt_in)
        if end_in is not None or enddt_in is not None:
            row.end_at = _to_dt(end_in or enddt_in)

        if getattr(event, "date", None) is not None:
            row.date = _to_date(event.date)
        if getattr(event, "end_date", None) is not None:
            row.end_date = _to_date(event.end_date)

        # Explicit clears (honor “provided but None”)
        if "start_at" in fields_set and getattr(event, "start_at", None) is None:
            row.start_at = None
        if "end_at" in fields_set and getattr(event, "end_at", None) is None:
            row.end_at = None
        if "datetime" in fields_set and getattr(event, "datetime", None) is None:
            row.start_at = None
        if "end_datetime" in fields_set and getattr(event, "end_datetime", None) is None:
            row.end_at = None
        if "date" in fields_set and getattr(event, "date", None) is None:
            row.date = None
        if "end_date" in fields_set and getattr(event, "end_date", None) is None:
            row.end_date = None

        # Validate final shape
        if row.all_day:
            if row.date is None or row.end_date is None:
                raise ValueError("all_day=True requires date and end_date")
            if row.start_at is not None or row.end_at is not None:
                raise ValueError("all_day=True cannot have start_at/end_at")
            if row.end_date <= row.date:
                raise ValueError("end_date must be > date")
        else:
            if row.start_at is None or row.end_at is None:
                raise ValueError("all_day=False requires start_at and end_at")
            if row.date is not None or row.end_date is not None:
                raise ValueError("all_day=False cannot have date/end_date")
            if row.end_at <= row.start_at:
                raise ValueError("end_at must be > start_at")

        if row.delete_scope not in ("single", "series", "this_and_following"):
            raise ValueError("delete_scope must be single|series|this_and_following")

        try:
            db.add(row)
            db.commit()
            return str(row.id)
        except IntegrityError:
            db.rollback()
            raise
