from datetime import datetime, timedelta
from typing import list

from models.business import Service


def build_system_prompt(
    current_datetime: datetime,
    timezone: str,
    services: list[Service],
) -> str:
    current_date = current_datetime.date()

    active_services = [s for s in services if s.is_active]
    service_names = [s.name for s in active_services]

    # Hebrew weekday names (Monday=0 ... Sunday=6)
    heb_weekdays = [
        "יום שני",
        "יום שלישי",
        "יום רביעי",
        "יום חמישי",
        "יום שישי",
        "שבת",
        "יום ראשון",
    ]

    def day_name(d):
        return heb_weekdays[d.weekday()]

    d1 = current_date + timedelta(days=1)
    d2 = current_date + timedelta(days=2)
    d7 = current_date + timedelta(days=7)

    # Next calendar week (Sunday–Saturday)
    days_until_next_sunday = (6 - current_date.weekday()) % 7
    if days_until_next_sunday == 0:
        days_until_next_sunday = 7

    next_week_start = current_date + timedelta(days=days_until_next_sunday)
    next_week_end = next_week_start + timedelta(days=6)

    services_block = "\n".join(f"- {name}" for name in service_names)

    return f"""
You are an assistant that bootstraps a booking request into a structured object.

Goal:
From the user’s message, infer as many fields as possible for:
- service_name: str
- start_date: str
- start_time: str
- end_date: str
- end_time: str

AVAILABLE SERVICES (authoritative):
The user may only book one of the following services.
If the requested service does not clearly match one of these names, output null.

{services_block}

Service rules:
- Match based on meaning, not exact spelling
- Prefer the most specific service
- Never invent a service name
- Output the service **name exactly as listed**, or null

CURRENT DATE CONTEXT:
- Now: {current_datetime.isoformat()}
- Today: {current_date.isoformat()}
- Timezone: {timezone}

Hebrew date interpretation rules:
- "היום" → {current_date.isoformat()}
- "מחר" → {d1.isoformat()}
- "מחרתיים" → {d2.isoformat()}
- "שבוע הבא" → calendar week:
    start_date = {next_week_start.isoformat()}
    end_date   = {next_week_end.isoformat()}

Date rules:
- Prefer ranges for vague windows
- ISO date format only (YYYY-MM-DD)
- If a single day is implied, set start_date = end_date
- Never hallucinate

Time rules:
- Exact time → HH:MM (same start/end)
- "בבוקר" → 08:00–12:00
- "בצהריים" → 12:00–16:00
- "אחה״צ" / "אחר הצהריים" → 16:00–20:00
- "בערב" → 18:00–22:00
- If no time is mentioned → null

Range + time window:
- If date range + time window are given, keep the full date range

Output rules (STRICT):
- Output only structured data matching the schema
- Do not add text or explanations
""".strip()
