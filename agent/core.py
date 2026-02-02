from openai import OpenAI
from pydantic import BaseModel
from dotenv import load_dotenv

from init_text import prompt

load_dotenv(".venv/.env")
client = OpenAI()


class CalendarEventBootstrap(BaseModel):
    service_name: str
    start_date: str
    end_date: str


def get_llm_bootstrap(user_input: str, system_prompt: str):
    response = client.responses.parse(
    model="gpt-5.2",
    input=[
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": user_input,
        },
    ],
    text_format=CalendarEventBootstrap,
)

    return response.output_parsed


if __name__ == "__main__":
    print(get_llm_bootstrap("יש תספורת שבוע הבא", prompt))