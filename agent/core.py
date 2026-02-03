from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from typing import Optional

from agent.init_text import build_system_prompt
from runtime.events import now_israel
from models.business import Service

# Load env
load_dotenv(".venv/.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI()


class CalendarEventBootstrap(BaseModel):
    service_name: str | None
    start_date: str | None
    end_date: str | None
    start_time: str | None
    end_time: str | None

    def is_empty(self) -> bool:
        return all(value is None or value == "" for value in self.model_dump().values())

    def has_any_date(self) -> bool:
        return self.start_date is not None or self.end_date is not None

    def has_any_time(self) -> bool:
        return self.start_time is not None or self.end_time is not None

    def has_any_date_or_time(self) -> bool:
        return self.has_any_date() or self.has_any_time()

    def has_service_name(self) -> bool:
        return self.service_name is not None

    def to_datetimes(self, timezone: str):
        return build_event_datetimes_with_day_bounds(self, timezone)


from datetime import datetime, time as dt_time  # <-- avoid collision with time module


def build_event_datetimes_with_day_bounds(
    bootstrap: CalendarEventBootstrap,
    timezone: str,
) -> tuple[Optional[datetime], Optional[datetime]]:
    tz = ZoneInfo(timezone)

    if not bootstrap.start_date:
        return None, None

    start_date = datetime.fromisoformat(bootstrap.start_date).date()
    end_date = (
        datetime.fromisoformat(bootstrap.end_date).date()
        if bootstrap.end_date
        else start_date
    )

    start_t = (
        dt_time.fromisoformat(bootstrap.start_time)
        if bootstrap.start_time
        else dt_time(0, 0)
    )
    end_t = (
        dt_time.fromisoformat(bootstrap.end_time)
        if bootstrap.end_time
        else dt_time(23, 59)
    )

    start_dt = datetime.combine(start_date, start_t, tzinfo=tz)
    end_dt = datetime.combine(end_date, end_t, tzinfo=tz)

    if end_dt < start_dt:
        raise ValueError("end_datetime cannot be before start_datetime")

    return start_dt, end_dt


def get_llm_bootstrap(user_input: str, services: list[Service]) -> CalendarEventBootstrap:
    system_prompt = build_system_prompt(
        current_datetime=now_israel(),
        timezone="Asia/Jerusalem",
        services=services,
    )

    response = client.responses.parse(
        model="gpt-5.2",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        text_format=CalendarEventBootstrap,
    )

    return response.output_parsed


import time as pytime  # <-- module alias to avoid clobbering dt_time


if __name__ == "__main__":
    start = pytime.perf_counter()

    services = [
        Service(id="1", name="פדיקור", duration_min=60, price=100),
        Service(id="2", name="פודיקור", duration_min=60, price=100),
    ]

    res = get_llm_bootstrap("אפשר תור פדיקור בחמישי?", services)

    elapsed_s = pytime.perf_counter() - start

    print(res)
    print(f"LLM bootstrap took {elapsed_s:.2f} seconds")
