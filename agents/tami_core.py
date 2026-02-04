from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from typing import Optional

from agent.tami_text import build_system_prompt
from runtime.events import now_israel
from models.business import Service
from handlers.utility import llm_iso_to_utc

# Load env
load_dotenv(".venv/.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI()


class ReminderBootstrap(BaseModel):
    title: str
    start: str
    end: str | None = None

from datetime import datetime, time as dt_time  # <-- avoid collision with time module


from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo


def _parse_iso_local_dt(value: str, tz: ZoneInfo) -> datetime:
    """
    Accepts:
      - YYYY-MM-DDTHH:MM
      - YYYY-MM-DD
      - (optionally) datetimes with offset, e.g. YYYY-MM-DDTHH:MM+02:00
    Returns timezone-aware datetime in tz.
    """
    if "T" not in value:
        # Date-only
        dt = datetime.fromisoformat(value)  # 00:00 naive
        dt = dt.replace(tzinfo=tz)
        return dt

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def build_event_datetimes_with_day_bounds(
    bootstrap,  # ReminderBootstrap
    timezone: str,
) -> tuple[Optional[datetime], Optional[datetime]]:
    tz = ZoneInfo(timezone)

    if not bootstrap.start:
        return None, None

    start_dt = _parse_iso_local_dt(bootstrap.start, tz)

    if bootstrap.end:
        end_dt = _parse_iso_local_dt(bootstrap.end, tz)
    else:
        end_dt = start_dt

    # If user gave date-only, expand to whole-day bounds (00:00–23:59)
    # We detect date-only by absence of "T" in the original string.
    if "T" not in bootstrap.start:
        start_dt = start_dt.replace(hour=0, minute=0)
    if bootstrap.end and "T" not in bootstrap.end:
        end_dt = end_dt.replace(hour=23, minute=59)
    elif (not bootstrap.end) and ("T" not in bootstrap.start):
        end_dt = start_dt.replace(hour=23, minute=59)

    if end_dt < start_dt:
        raise ValueError("end_datetime cannot be before start_datetime")

    return start_dt, end_dt

def get_llm_simple_reminders(user_input: str) -> ReminderBootstrap:
    system_prompt = build_system_prompt(
        current_datetime=now_israel(),
        timezone="Asia/Jerusalem",
    )

    response = client.responses.parse(
        model="gpt-5.1",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        text_format=ReminderBootstrap,
    )

    return response.output_parsed


import time as pytime  # <-- module alias to avoid clobbering dt_time


if __name__ == "__main__":
    start = pytime.perf_counter()
    text = "תזכיר לי עוד 5 דקות לעשן"

    texts = [
        "תזכיר לי עוד 5 דקות לעשן",
        "תזכיר לי בשתיים לצחצח שיניים",
        "תעשה תזכורת למחר בערב להתקשר לחיים"
        
    ]
    
    for text in texts:
        res = get_llm_simple_reminders(text)

        elapsed_s = pytime.perf_counter() - start

        print(res)
        print(llm_iso_to_utc(res.start))
        print(f"LLM bootstrap took {elapsed_s:.2f} seconds")
