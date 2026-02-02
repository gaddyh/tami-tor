from openai import OpenAI
from pydantic import BaseModel
from dotenv import load_dotenv

from agent.init_text import build_system_prompt
from runtime.events import now_israel

load_dotenv(".venv/.env")
client = OpenAI()


class CalendarEventBootstrap(BaseModel):
    service_name: str | None
    start_date: str | None
    end_date: str | None
    start_time: str | None
    end_time: str | None

    def is_empty(self) -> bool:
        return all(
            value is None or value == ""
            for value in self.model_dump().values()
        )

    def has_any_date(self) -> bool:
        return self.start_date is not None or self.end_date is not None

    def has_any_time(self) -> bool:
        return self.start_time is not None or self.end_time is not None

    def has_any_date_or_time(self) -> bool:
        return self.has_any_date() or self.has_any_time()

    def has_service_name(self) -> bool:
        return self.service_name is not None


def get_llm_bootstrap(user_input: str):
    system_prompt = build_system_prompt(
        current_datetime=now_israel(),
        timezone="Asia/Jerusalem",
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


import time

if __name__ == "__main__":
    start = time.perf_counter()

    res = get_llm_bootstrap("יש פדיקור שבוע הבא אחה״צ?")

    elapsed_ms = (time.perf_counter() - start)

    print(res)
    print(f"LLM bootstrap took {elapsed_ms:.2f} seconds")

