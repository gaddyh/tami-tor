# db/fetch_events.py
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, Sequence

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from db.session import SessionLocal
from models.calendar_event import EventRow


def fetch_future_events(
    *,
    user_id: str,
    now: Optional[datetime] = None,
    limit: int = 100,
    include_all_day: bool = True,
    include_cancelled: bool = False,
) -> list[EventRow]:
    """
    Return future events for a user from the DB.

    Handles:
    - timed events: start_at/end_at (timestamp columns)
    - all-day events: date/end_date (date columns)
    """

    if not user_id:
        raise ValueError("user_id is required")

    now = now or datetime.utcnow()
    today = now.date()

    status_filter = True if include_cancelled else (EventRow.status != "cancelled")

    # "Future" logic:
    # - timed: end_at > now  (so ongoing events still show up)
    # - all-day: end_date > today (exclusive end)
    timed_pred = and_(EventRow.all_day.is_(False), EventRow.end_at.isnot(None), EventRow.end_at > now)

    if include_all_day:
        all_day_pred = and_(
            EventRow.all_day.is_(True),
            EventRow.end_date.isnot(None),
            EventRow.end_date > today,
        )
        future_pred = or_(timed_pred, all_day_pred)
    else:
        future_pred = timed_pred

    with SessionLocal() as db:
        q = (
            db.query(EventRow)
            .filter(EventRow.client_id == user_id)
            .filter(status_filter)
            .filter(future_pred)
            # Ordering:
            # - timed events by start_at
            # - all-day by date
            .order_by(
                EventRow.start_at.asc().nullslast(),
                EventRow.date.asc().nullslast(),
                EventRow.created_at.asc() if hasattr(EventRow, "created_at") else EventRow.id.asc(),
            )
            .limit(limit)
        )
        return list(q.all())


def fetch_future_events_as_dicts(
    *,
    user_id: str,
    now: Optional[datetime] = None,
    limit: int = 100,
    include_all_day: bool = True,
    include_cancelled: bool = False,
) -> list[dict]:
    """
    Same as fetch_future_events, but returns JSON-friendly dicts.
    """
    rows = fetch_future_events(
        user_id=user_id,
        now=now,
        limit=limit,
        include_all_day=include_all_day,
        include_cancelled=include_cancelled,
    )

    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": str(r.id),
                "title": r.title,
                "description": getattr(r, "description", None),
                "location": getattr(r, "location", None),
                "timezone": getattr(r, "timezone", None),
                "all_day": bool(getattr(r, "all_day", False)),
                "start_at": r.start_at.isoformat() if r.start_at else None,
                "end_at": r.end_at.isoformat() if r.end_at else None,
                "date": r.date.isoformat() if r.date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "gcal_event_id": getattr(r, "gcal_event_id", None),
                "status": getattr(r, "status", None),
                "participants": getattr(r, "participants", None),
                "recurrence": getattr(r, "recurrence", None),
                "reminders": getattr(r, "reminders", None),
            }
        )
    return out
