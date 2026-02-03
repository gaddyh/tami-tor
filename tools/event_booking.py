from __future__ import annotations
from typing import Any, Optional, Literal, List, Dict
from observability.obs import span_attrs, mark_error, instrument_io
from models.event_item import EventItem
from adapters.google.process_event import _process_event

def summarize(result: dict):
    return result

def redact(event: EventItem):
    return event

@instrument_io(
    name="tool.create_event",
    meta={"agent": "tami", "operation": "tool", "tool": "create_event", "schema": "EventItem.v1"},
    input_fn=lambda user_id, event: {
        "user_id": user_id,
        # ↓ serialize Pydantic model for the instrumentation layer
        "event": (event.model_dump(mode="json") if hasattr(event, "model_dump")
                  else event.dict() if hasattr(event, "dict")
                  else event)
    },
    output_fn=summarize,
    redact=True,
)
def create_event(user_id: str, event: EventItem):
    with span_attrs("tool.create_event", agent="tami", operation="tool", tool="create_event") as s:
        # ↓ serialize before redaction/logging to avoid .items() on a model
        _event_dict = (event.model_dump(mode="json") if hasattr(event, "model_dump")
                       else event.dict() if hasattr(event, "dict")
                       else event)
        s.update(input={"args": redact(_event_dict)})
        try:
            out = _process_event(user_id, event)
            s.update(output=summarize(out))
            return out
        except Exception as e:
            mark_error(e, kind="ToolError.process_event", span=s)
            raise

from datetime import datetime, date
from typing import Sequence


def _fmt_dt(dt: datetime) -> str:
    # דוגמה: ג׳ 12 מרץ, 14:30
    return dt.strftime("%d/%m/%Y בשעה %H:%M")


def _fmt_date(d: date) -> str:
    # דוגמה: 12/03/2026
    return d.strftime("%d/%m/%Y")


def format_events_message_he(events: Sequence[dict]) -> str:
    """
    מקבל רשימת אירועים (dictים)
    ומחזיר הודעה למשתמש בעברית
    """

    # ---------- אין אירועים ----------
    if not events:
        return (
            "📅 אין לך אירועים עתידיים ביומן.\n\n"
            "רוצה שאעזור לך לקבוע פגישה חדשה?"
        )

    # ---------- אירוע אחד ----------
    if len(events) == 1:
        e = events[0]

        if e.get("all_day"):
            when = f"{_fmt_date(date.fromisoformat(e['date']))} (כל היום)"
        else:
            start = datetime.fromisoformat(e["start_at"])
            end = datetime.fromisoformat(e["end_at"])
            when = f"{_fmt_dt(start)} – {_fmt_dt(end)}"

        lines = [
            "📅 *האירוע הקרוב שלך:*",
            f"*{e['title']}*",
            when,
        ]

        if e.get("location"):
            lines.append(f"📍 {e['location']}")

        return "\n".join(lines)

    # ---------- כמה אירועים ----------
    lines = ["📅 *האירועים הקרובים שלך:*"]

    for i, e in enumerate(events[:5], start=1):
        if e.get("all_day"):
            when = f"{_fmt_date(date.fromisoformat(e['date']))} (כל היום)"
        else:
            start = datetime.fromisoformat(e["start_at"])
            when = _fmt_dt(start)

        lines.append(f"{i}. {when} — {e['title']}")

    remaining = len(events) - 5
    if remaining > 0:
        lines.append(f"\n…ועוד {remaining} אירועים נוספים.")

    lines.append("\nרוצה פרטים על אחד מהם, או שנקבע פגישה חדשה?")

    return "\n".join(lines)
