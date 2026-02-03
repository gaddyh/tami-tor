from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timezone
from typing import Optional, List, Any
import uuid as uuid_lib

from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError

from db.session import SessionLocal
from models.calendar_event import EventRow  # your SQLAlchemy EventItem model
from adapters.google.tokens import get_valid_credentials

def init_google_calendar(user_id: str):
    creds = get_valid_credentials(user_id)
    service = build('calendar', 'v3', credentials=creds)
    return service

@dataclass
class VerifiedEvent:
    row: EventRow
    gcal: Optional[dict]          # the Google event object, if fetched
    verified: bool               # True if Google event exists and matches (loosely)
    reason: Optional[str] = None # why not verified (missing id / not found / mismatch)


def _gcal_dt_to_iso(gcal_dt: Optional[dict]) -> Optional[str]:
    """
    Google event start/end look like:
      {"dateTime": "2026-02-03T12:00:00+02:00", "timeZone": "Asia/Jerusalem"}
    or for all-day:
      {"date": "2026-02-03"}
    """
    if not gcal_dt:
        return None
    return gcal_dt.get("dateTime") or gcal_dt.get("date")


def get_future_events_verified(
    *,
    user_id: str,
    limit: int = 50,
    sync_from_gcal: bool = True, # if True, update DB fields from Google event
    include_rows_without_gcal_id: bool = False,
) -> List[VerifiedEvent]:
    """
    Fetch future events from DB and verify each against Google Calendar using gcal_event_id.

    Future definition:
      - timed events: datetime >= now (UTC comparison; stored as timestamptz)
      - all-day events: date >= today
    """
    if not user_id:
        raise ValueError("user_id is required")

    gcal_service = init_google_calendar(user_id)
    now_utc = datetime.now(timezone.utc)
    today = date.today()

    with SessionLocal() as db:
        q = (
            db.query(EventRow)
            .filter(EventRow.user_id == user_id)
            .filter(EventRow.status != "deleted")
            .filter(
                or_(
                    and_(EventRow.all_day == False, EventRow.start_at >= now_utc),
                    and_(EventRow.all_day == True, EventRow.date >= today),
                )
            )
            .order_by(
                # keep ordering stable: soonest first
                EventRow.all_day.asc(),
                EventRow.start_at.asc().nullslast(),
                EventRow.date.asc().nullslast(),
            )
            .limit(limit)
        )

        rows: List[EventRow] = list(q.all())

        out: List[VerifiedEvent] = []

        for row in rows:
            # If no gcal_event_id, you can't verify against Google.
            if not row.gcal_event_id:
                if include_rows_without_gcal_id:
                    out.append(VerifiedEvent(row=row, gcal=None, verified=False, reason="missing_gcal_event_id"))
                continue

            # Fetch from Google Calendar
            try:
                gcal_event = (
                    gcal_service.events()
                    .get(calendarId="primary", eventId=row.gcal_event_id)
                    .execute()
                )
            except Exception as e:
                # Common: 404 notFound if the event was deleted or id is wrong
                msg = str(e)
                # Optional: mark as deleted locally if Google says not found
                if "404" in msg or "notFound" in msg:
                    row.status = "deleted"
                    db.add(row)
                    db.commit()
                    out.append(VerifiedEvent(row=row, gcal=None, verified=False, reason="gcal_not_found_marked_deleted"))
                    continue

                out.append(VerifiedEvent(row=row, gcal=None, verified=False, reason=f"gcal_error:{msg}"))
                continue

            # Basic consistency check (lightweight)
            g_start = gcal_event.get("start")
            g_end = gcal_event.get("end")
            g_start_iso = _gcal_dt_to_iso(g_start)
            g_end_iso = _gcal_dt_to_iso(g_end)

            verified = True
            reason = None

            # Verify shape matches (all-day vs timed)
            if row.all_day:
                if not (g_start and g_start.get("date")):
                    verified = False
                    reason = "shape_mismatch_expected_all_day"
            else:
                if not (g_start and g_start.get("dateTime")):
                    verified = False
                    reason = "shape_mismatch_expected_timed"

            # Optional: sync fields from Google into DB (useful if users edit in Google Calendar)
            if sync_from_gcal and verified:
                # title/description/location/timezone
                row.title = gcal_event.get("summary") or row.title
                row.description = gcal_event.get("description") if gcal_event.get("description") is not None else row.description
                row.location = gcal_event.get("location") if gcal_event.get("location") is not None else row.location
                row.timezone = (g_start or {}).get("timeZone") or row.timezone

                if row.all_day:
                    # Google uses exclusive end date for all-day events
                    if g_start_iso:
                        row.date = date.fromisoformat(g_start_iso)
                    if g_end_iso:
                        row.end_date = date.fromisoformat(g_end_iso)
                    # ensure timed fields cleared
                    row.start_at = None
                    row.end_at = None
                else:
                    if g_start_iso:
                        row.start_at = datetime.fromisoformat(g_start_iso)
                    if g_end_iso:
                        row.end_at = datetime.fromisoformat(g_end_iso)
                    # ensure date fields cleared
                    row.date = None
                    row.end_date = None

                # Participants/reminders/recurrence are more nuanced to map reliably;
                # keep them as-is unless you want a specific mapping.
                db.add(row)
                db.commit()

            out.append(VerifiedEvent(row=row, gcal=gcal_event, verified=verified, reason=reason))

        return out
