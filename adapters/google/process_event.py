from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from models.event_item import EventItem
from adapters.google.tokens import get_valid_credentials

from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo
from adapters.google.util import _iso_to_rfc5545_z, _normalize_byday, _FREQ_MAP
from observability.obs import span_attrs, mark_error

def _to_rfc3339(dt_in: str | datetime, *, default_tz: ZoneInfo) -> str:
    """
    Return RFC3339 dateTime with explicit offset, interpreting naive as Asia/Jerusalem.
    Accepts str (ISO-ish) or datetime.
    """
    if isinstance(dt_in, str):
        # allow "YYYY-MM-DDTHH:MM[:SS][±HH:MM]" or with Z
        dt = datetime.fromisoformat(dt_in.replace("Z", "+00:00")) if "T" in dt_in else datetime.fromisoformat(dt_in)
    else:
        dt = dt_in

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = dt.replace(tzinfo=default_tz)

    return dt.isoformat()

def build_event_body(event: EventItem) -> dict:
    """Builds a Google Calendar event body from EventItem kwargs with strict mapping/recurrence."""
    body = {}

    # summary (title) — only include if present
    title = event.title
    if title:
        body["summary"] = title

    # optional description
    desc = event.description
    if desc:
        body["description"] = desc

    # optional location
    loc = event.location
    if loc:
        body["location"] = loc

    tz_name = event.timezone

    # --- Timed vs all-day ----------------------------------------------------
    if event.all_day:
        d0 = event.date
        d1 = event.end_date
        if not d0:
            raise ValueError("Missing date for all-day event")

        d0_obj = date.fromisoformat(d0)
        d1_obj = date.fromisoformat(d1) if d1 else (d0_obj + timedelta(days=1))

        body["start"] = {"date": d0_obj.isoformat()}
        body["end"]   = {"date": d1_obj.isoformat()}
    else:
        if event.start_at:
            tz = ZoneInfo(tz_name)
            start_dt = _to_rfc3339(event.start_at, default_tz=tz)

            if event.end_at:
                end_dt = _to_rfc3339(event.end_at, default_tz=tz)
            else:
                # default duration: +1 hour
                start_native = event.start_at
                if isinstance(start_native, str):
                    # parse ISO; accept trailing 'Z'
                    start_native = datetime.fromisoformat(start_native.replace("Z", "+00:00"))
                end_dt = _to_rfc3339(start_native + timedelta(hours=1), default_tz=tz)

            body["start"] = {"dateTime": start_dt, "timeZone": tz_name}
            body["end"]   = {"dateTime": end_dt,   "timeZone": tz_name}

    # --- Optional fields -----------------------------------------------------
    if event.location:
        body["location"] = event.location

    # Attendees: map to Google's shape (displayName/responseStatus)
    if event.participants:
        attendees = []
        for p in event.participants:
            if not getattr(p, "email", None):
                continue
            a = {"email": p.email}
            if getattr(p, "name", None):
                a["displayName"] = p.name
            if getattr(p, "status", None):
                a["responseStatus"] = p.status
            attendees.append(a)
        if attendees:
            body["attendees"] = attendees

    # Reminders: wrap overrides; if absent, Google uses defaults
    if event.reminders is not None:
        overrides = [
            {"method": r.method, "minutes": int(r.minutes)}
            for r in event.reminders
        ]
        if overrides:
            body["reminders"] = {"useDefault": False, "overrides": overrides}
        else:
            body["reminders"] = {"useDefault": True}

    # --- Recurrence (RRULE) --------------------------------------------------
    # Supports your model: freq, interval, by_day, by_month_day, until, count
    rec = event.recurrence
    if rec:
        freq_in = getattr(rec, "freq", None)
        if not freq_in:
            raise ValueError("recurrence.freq is required")

        # FREQ
        try:
            freq = _FREQ_MAP[freq_in.lower()]
        except KeyError:
            raise ValueError(f"Unsupported recurrence.freq: {freq_in}")

        parts = [f"FREQ={freq}"]

        # INTERVAL
        interval = getattr(rec, "interval", None)
        if interval and int(interval) != 1:
            parts.append(f"INTERVAL={int(interval)}")

        # BYDAY
        by_day = getattr(rec, "by_day", None)
        if by_day:
            parts.append(f"BYDAY={','.join(_normalize_byday(by_day))}")

        # BYMONTHDAY
        by_md = getattr(rec, "by_month_day", None)
        if by_md:
            if not all(isinstance(x, int) for x in by_md):
                raise ValueError("recurrence.by_month_day must be a list of integers")
            parts.append(f"BYMONTHDAY={','.join(str(x) for x in by_md)}")

        # COUNT vs UNTIL (mutually exclusive)
        until = getattr(rec, "until", None)
        count = getattr(rec, "count", None)
        if until and count:
            raise ValueError("Use either recurrence.count or recurrence.until, not both")

        if count:
            parts.append(f"COUNT={int(count)}")
        elif until:
            parts.append(f"UNTIL={_iso_to_rfc5545_z(until)}")

        body["recurrence"] = [f"RRULE:{';'.join(parts)}"]

    return body

def _iso_to_dt(s: str) -> datetime:
    """Parse RFC3339/ISO; accepts 'Z' by normalizing to +00:00."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)

def _body_time_range(
    body: dict,
    fallback_tz: str | None = None,
    *,
    allow_missing: bool = True
) -> tuple[datetime | None, datetime | None]:
    """
    Extract (start, end) from a body object (insert/patch).
    - On all-day start (date), default end = +1 day.
    - If both start and end are missing and allow_missing=True, return (None, None)
      so caller can inherit times from the existing event.
    """
    start = (body or {}).get("start") or {}
    end   = (body or {}).get("end") or {}

    if not start and not end:
        if allow_missing:
            return None, None
        raise ValueError("Missing start date/dateTime")

    tz_name = start.get("timeZone") or end.get("timeZone") or fallback_tz
    tz = ZoneInfo(tz_name) if (ZoneInfo and tz_name) else timezone.utc

    # --- start ---
    if "dateTime" in start:
        sdt = _iso_to_dt(start["dateTime"])
    elif "date" in start:
        sdt = datetime.fromisoformat(start["date"] + "T00:00:00").replace(tzinfo=tz)
    else:
        if allow_missing and end:
            # Rare: end given without start; let caller decide fallback.
            return None, None
        raise ValueError("Missing start date/dateTime")

    # --- end ---
    if end:
        if "dateTime" in end:
            edt = _iso_to_dt(end["dateTime"])
        elif "date" in end:
            edt = datetime.fromisoformat(end["date"] + "T00:00:00").replace(tzinfo=tz)
        else:
            raise ValueError("Bad end (neither dateTime nor date)")
    else:
        # Default: +1 day for all-day, else +60 minutes
        edt = sdt + (timedelta(days=1) if "date" in start and "dateTime" not in start else timedelta(hours=1))

    return sdt, edt

from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("Naive datetime passed; must be tz-aware")
    return dt

def _to_utc(dt: datetime) -> datetime:
    return _ensure_aware(dt).astimezone(timezone.utc)

def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    # assume all arguments are tz-aware and in the SAME zone (we’ll use UTC)
    return (a_start < b_end) and (a_end > b_start)

def _event_time_range(item: dict, default_tz: str) -> tuple[datetime, datetime]:
    """
    Returns (start_utc, end_utc) for a Google Calendar event.
    Handles dateTime and all-day date forms. Uses default_tz when needed.
    """
    tz = ZoneInfo(default_tz)

    s = item.get("start", {})
    e = item.get("end", {})

    # dateTime case (has an offset). Example: "2025-11-12T17:00:00+02:00"
    if "dateTime" in s and "dateTime" in e:
        sdt = datetime.fromisoformat(s["dateTime"])  # already aware (has offset)
        edt = datetime.fromisoformat(e["dateTime"])
        return _to_utc(sdt), _to_utc(edt)

    # all-day case (date only). Google semantics: [date 00:00, next_date 00:00) in the calendar’s local tz
    if "date" in s and "date" in e:
        # end.date is exclusive; both are ISO dates (YYYY-MM-DD)
        s_local = datetime.combine(date.fromisoformat(s["date"]), datetime.min.time(), tzinfo=tz)
        e_local = datetime.combine(date.fromisoformat(e["date"]), datetime.min.time(), tzinfo=tz)
        return _to_utc(s_local), _to_utc(e_local)

    # Mixed or missing → fall back defensively
    raise ValueError("Unrecognized event time shape")

def _find_conflicts(service, calendar_id: str, user_tz: str, start: datetime, end: datetime,
                    exclude_event_id: str | None = None) -> list[dict]:
    # Normalize request window to UTC
    start_utc = _to_utc(start)
    end_utc   = _to_utc(end)

    # widen window to catch expansions; Google expects RFC3339 with offset or Z
    time_min = (start_utc - timedelta(days=1)).isoformat()
    time_max = (end_utc   + timedelta(days=1)).isoformat()

    page_token = None
    conflicts: list[dict] = []

    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            singleEvents=True,        # expand recurrences
            showDeleted=False,
            orderBy="startTime",
            timeMin=time_min,
            timeMax=time_max,
            pageToken=page_token,
        ).execute()

        for it in resp.get("items", []):
            if it.get("status") == "cancelled":
                continue
            if exclude_event_id and it.get("id") == exclude_event_id:
                continue
            if (it.get("transparency") or "").lower() == "transparent":
                continue

            try:
                sdt_utc, edt_utc = _event_time_range(it, default_tz=user_tz)
            except Exception:
                continue

            if _overlaps(start_utc, end_utc, sdt_utc, edt_utc):
                # provide human-facing times back in the user tz so they read as 17:00 etc.
                tz = ZoneInfo(user_tz)
                conflicts.append({
                    "id": it.get("id"),
                    "title": it.get("summary") or "(ללא כותרת)",
                    "start": sdt_utc.astimezone(tz).isoformat(timespec="minutes"),
                    "end":   edt_utc.astimezone(tz).isoformat(timespec="minutes"),
                })

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return conflicts


# --- Tool --------------------------------------------------------------------

def _process_event(user_id: str, event: EventItem) -> dict:
    """
    Create, update, or delete a Google Calendar event for the given user.
    Supports timed and all-day events.
    Returns:
      { ok: bool,
        item_id: str|None,
        error: str|None,
        code: str|None,
        conflicts?: [ {id,title,start,end}, ... ]  # present only when code == 'slot_taken'
      }
    """
    try:
        creds = get_valid_credentials(user_id)
        if not creds:
            return {"ok": False, "item_id": None, "error": "No valid credentials", "code": "no_creds"}

        service = build("calendar", "v3", credentials=creds)
        calendar_id = "primary"

        command = event.command
        event_id = event.item_id
        force = bool(getattr(event, "force", False))

        if command in ("update", "delete") and not event_id:
            return {"ok": False, "item_id": None, "error": "Missing event_id", "code": "no_id"}

        # Build desired body first (so we can infer target times)
        body = build_event_body(event) if command in ("create", "update") else {}

        current1 = None
        if command == "update":
            current1 = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            # If caller didn't provide start/end in the body, inherit from current event
            if not body.get("start") and not body.get("end"):
                body["start"] = current1.get("start", {})
                body["end"]   = current1.get("end", {})

        # --- Decide sendUpdates (Google email invitations/updates) -----------
        # Priority:
        # 1) explicit 'send_updates' in kwargs if provided (expects 'all'|'externalOnly'|'none')
        # 2) legacy/boolean 'notify' if provided (True -> 'all', False -> 'none')
        # 3) default: if attendees present -> 'all' else 'none'
        explicit = None
        su = getattr(event, "send_updates", None)
        if isinstance(su, str):
            explicit = su.strip().lower()
        notify_flag = bool(getattr(event, "notify", False))

        send_updates = "all"
        has_attendees = bool(body.get("attendees"))
        print("has_attendees", has_attendees)
        print("attendees", body.get("attendees"))
        if not has_attendees:
            send_updates = "none"

        if has_attendees:
                user = get_user(user_id)
                runtime = getattr(user, "runtime", None)
                if runtime is not None:
                    if not hasattr(runtime, "contacts") or not isinstance(runtime.contacts, dict):
                        runtime.contacts = {}
                    for a in body.get("attendees", []):
                        name = (a.get("displayName") or a.get("name") or a.get("email") or "").strip()
                        if not name:
                            continue
                        email = (a.get("email") or "").strip().lower()
                        contact = runtime.contacts.setdefault(name, {})
                        if email:
                            contact["email"] = email
                            user.runtime.add_prefered_contact(name, contact)

                        print("runtime.contacts process event", runtime.contacts[name])
                    UserStore(user_id).save(user)

        # ----- DELETE ---------------------------------------------------------
        delete_scope = (getattr(event, "delete_scope", "single") or "single").lower()

        if command == "delete":
            # Fetch the event to know if it's an instance of a recurring series
            try:
                current = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            except Exception as e:
                return {"ok": False, "item_id": None, "error": f"get failed: {e}", "code": "no_id"}

            # If it's an expanded instance it will have recurringEventId + originalStartTime
            is_instance = bool(current.get("recurringEventId") and current.get("originalStartTime"))

            if delete_scope == "series":
                # If user passed an instance id, delete the parent/master
                master_id = current.get("recurringEventId") if is_instance else current.get("id")
                service.events().delete(
                    calendarId=calendar_id,
                    eventId=master_id,
                    sendUpdates=send_updates,
                ).execute()
                return {"ok": True, "item_id": master_id, "error": None, "code": None}

            elif delete_scope == "this_and_following":
                if not is_instance:
                    return {
                        "ok": False, "item_id": None,
                        "error": "this_and_following requires an occurrence (instance) id",
                        "code": "bad_input"
                    }

                # Load master
                master = service.events().get(calendarId=calendar_id, eventId=current["recurringEventId"]).execute()

                # Determine instance start (prefer dateTime; else treat all-day as 00:00 in master TZ if present)
                ost = current["originalStartTime"]
                if "dateTime" in ost:
                    inst_iso = ost["dateTime"].replace("Z", "+00:00")
                    inst_dt = datetime.fromisoformat(inst_iso)
                else:
                    # all-day: build an aware dt at midnight in master/start tz if provided, else UTC
                    tz_name = (master.get("start", {}) or {}).get("timeZone") \
                            or (master.get("end", {}) or {}).get("timeZone")
                    tz = ZoneInfo(tz_name) if tz_name else timezone.utc
                    inst_dt = datetime.fromisoformat(ost["date"] + "T00:00:00").replace(tzinfo=tz)

                # UNTIL must be BEFORE the occurrence (inclusive semantics)
                until_just_before = (inst_dt.astimezone(timezone.utc) - timedelta(seconds=1))
                until_rfc5545 = until_just_before.strftime("%Y%m%dT%H%M%SZ")

                rec = (master.get("recurrence") or [])
                if not rec or not any(r.startswith("RRULE:") for r in rec):
                    return {"ok": False, "item_id": None, "error": "Master has no RRULE; cannot split", "code": "unsupported"}

                new_rrules = []
                for r in rec:
                    if not r.startswith("RRULE:"):
                        new_rrules.append(r)
                        continue
                    parts = r[len("RRULE:"):].split(";")
                    # Drop COUNT/UNTIL if present, then set UNTIL to just before the instance
                    parts = [p for p in parts if not p.startswith("UNTIL=") and not p.startswith("COUNT=")]
                    parts.append(f"UNTIL={until_rfc5545}")
                    new_rrules.append("RRULE:" + ";".join(parts))

                service.events().patch(
                    calendarId=calendar_id,
                    eventId=master["id"],
                    body={"recurrence": new_rrules},
                    sendUpdates=send_updates,
                ).execute()

                return {"ok": True, "item_id": master["id"], "error": None, "code": None}

            else:
                # single (default): delete only this event id (instance or single non-recurring)
                service.events().delete(
                    calendarId=calendar_id,
                    eventId=event_id,
                    sendUpdates=send_updates,
                ).execute()
                return {"ok": True, "item_id": event_id, "error": None, "code": None}

        # ----- CREATE / UPDATE -----------------------------------------------
        current = None
        if command == "update":
            current = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        # Determine target interval (start, end)
        if command == "create":
            target_start, target_end = _body_time_range(
                body, fallback_tz=(body.get("start") or {}).get("timeZone")
            )
        else:  # UPDATE
            if not body.get("start") and not body.get("end"):
                # Caller didn't provide times → inherit existing event's times
                target_start, target_end = _event_time_range(current, default_tz=event.timezone)
            else:
                # Caller provided (partial or full) time edits → compute from body
                # allow_missing=False enforces correctness when times are being changed
                new_start, new_end = _body_time_range(
                    body, fallback_tz=(body.get("start") or {}).get("timeZone"), allow_missing=False
                )
                # If only one side provided, keep duration/start from current
                cur_start, cur_end = _event_time_range(current, default_tz=event.timezone)
                if new_start is None and new_end is not None:
                    new_start = cur_start
                if new_end is None and new_start is not None:
                    new_end = new_start + (cur_end - cur_start)

                target_start, target_end = new_start, new_end

                # Normalize the patch body to match computed datetimes/all-day
                if "dateTime" in (body.get("start") or {}) or "dateTime" in (body.get("end") or {}):
                    body.setdefault("start", {})["dateTime"] = target_start.isoformat()
                    body.setdefault("end", {})["dateTime"] = target_end.isoformat()
                    body["start"].pop("date", None); body["end"].pop("date", None)
                else:
                    body.setdefault("start", {})["date"] = target_start.date().isoformat()
                    body.setdefault("end", {})["date"] = target_end.date().isoformat()
                    body["start"].pop("dateTime", None); body["end"].pop("dateTime", None)

        if target_end <= target_start:
            print(f"target_end: {target_end}, target_start: {target_start}")
            return {"ok": False, "item_id": None, "error": "end <= start", "code": "bad_input"}

        exclude_id = event_id if command == "update" else None
        print("exclude_id: ", exclude_id)
        conflicts = _find_conflicts(service, calendar_id, user_tz=event.timezone, start=target_start, end=target_end, exclude_event_id=exclude_id)
        print("conflicts: ", conflicts)
        if conflicts and len(conflicts) > 0 and not force:
            return {
                "ok": False,
                "item_id": None,
                "error": "Requested time slot is taken",
                "code": "slot_taken",
                "conflicts": conflicts,
            }

        if command == "create":
            evt = service.events().insert(
                calendarId=calendar_id,
                body=body,
                sendUpdates=send_updates,
            ).execute()
            return {"ok": True, "item_id": evt["id"], "error": None, "code": None}

        elif command == "update":
            evt = service.events().patch(
                calendarId=calendar_id,
                eventId=event_id,
                body=body,
                sendUpdates=send_updates,
            ).execute()
            return {"ok": True, "item_id": evt["id"], "error": None, "code": None}

        else:
            return {"ok": False, "item_id": None, "error": f"Unsupported command: {command}", "code": "bad_command"}

    except ValueError as ve:
        mark_error(ve, kind="ProcessEventValueError")
        return {"ok": False, "item_id": None, "error": str(ve), "code": "bad_input"}
    except Exception as e:
        mark_error(e, kind="ProcessEventException")
        return {"ok": False, "item_id": None, "error": str(e), "code": "exception"}

if __name__ == "__main__":
    eventJson = {
    "command": "create",
    "title": "לעשות הזמנת חלב",
    "datetime": "2025-11-20T10:00:00+02:00",
    "timezone": "Asia/Jerusalem",
    "item_type": "event",
    "recurrence": {
      "freq": "weekly",
      "by_day": [
        "TH"
      ],
      "interval": 1
    }
}
    event = EventItem(**eventJson)
    ctx = RunContextWrapper(AppCtx(user_id="972546610653", user_name="me", thread_id="asdasd", default_tz="Asia/Jerusalem", current_datetime=datetime.now()))
    result = _process_event(ctx, event)
    print(result)
