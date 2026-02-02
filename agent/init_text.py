from datetime import datetime, timedelta
from typing import List

from models.business import Service


def build_system_prompt(
    current_datetime: datetime,
    timezone: str,
    services: List[Service],
) -> str:
    current_date = current_datetime.date()

    active_services = [s for s in services if s.is_active]
    service_names = [s.name for s in active_services]

    # Python weekday(): Monday=0 ... Sunday=6
    heb_weekdays = [
        "יום שני",     # 0
        "יום שלישי",   # 1
        "יום רביעי",   # 2
        "יום חמישי",   # 3
        "יום שישי",    # 4
        "שבת",         # 5
        "יום ראשון",   # 6
    ]

    def day_name(d):
        return heb_weekdays[d.weekday()]

    # Next 7 days (useful for resolving "ביום חמישי" etc.)
    d1 = current_date + timedelta(days=1)
    d2 = current_date + timedelta(days=2)
    d3 = current_date + timedelta(days=3)
    d4 = current_date + timedelta(days=4)
    d5 = current_date + timedelta(days=5)
    d6 = current_date + timedelta(days=6)
    d7 = current_date + timedelta(days=7)

    # Next calendar week (Sunday–Saturday)
    days_until_next_sunday = (6 - current_date.weekday()) % 7
    if days_until_next_sunday == 0:
        days_until_next_sunday = 7

    next_week_start = current_date + timedelta(days=days_until_next_sunday)  # Sunday
    next_week_end = next_week_start + timedelta(days=6)  # Saturday

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
- Output the service name exactly as listed, or null

CURRENT DATE CONTEXT:
- Now: {current_datetime.isoformat()}
- Today: {current_date.isoformat()}
- Timezone: {timezone}

NEXT 7 DAYS (authoritative mapping for weekday mentions):
- {day_name(d1)}: {d1.isoformat()}
- {day_name(d2)}: {d2.isoformat()}
- {day_name(d3)}: {d3.isoformat()}
- {day_name(d4)}: {d4.isoformat()}
- {day_name(d5)}: {d5.isoformat()}
- {day_name(d6)}: {d6.isoformat()}
- {day_name(d7)}: {d7.isoformat()}

Hebrew date interpretation rules:
- "היום" → {current_date.isoformat()}
- "מחר" → {d1.isoformat()}
- "מחרתיים" → {d2.isoformat()}
- "ביום <weekday>" (e.g. "בחמישי", "ביום חמישי") → choose the next occurrence of that weekday from Today (prefer within NEXT 7 DAYS).
- "שבוע הבא" → calendar week (Israel convention Sunday–Saturday):
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

OUTPUT FORMAT (STRICT):
Return ONLY a JSON object with exactly these keys:
service_name, start_date, start_time, end_date, end_time
Use null for unknowns.
No extra text.

EXAMPLES (input → output):

1) Input: "אני רוצה לקבוע תור"
Output:
{{"service_name": null, "start_date": null, "start_time": null, "end_date": null, "end_time": null}}

2) Input: "אני רוצה תור לציפורניים"
Output:
{{"service_name": "ציפורניים", "start_date": null, "start_time": null, "end_date": null, "end_time": null}}

3) Input: "יש תספורת שבוע הבא"
Output:
{{"service_name": "תספורת", "start_date": "{next_week_start.isoformat()}", "start_time": null, "end_date": "{next_week_end.isoformat()}", "end_time": null}}

4) Input: "יש תספורת מחר בשתיים?"
Output:
{{"service_name": "תספורת", "start_date": "{d1.isoformat()}", "start_time": "14:00", "end_date": "{d1.isoformat()}", "end_time": "14:00"}}

5) Input: "יש פדיקור שבוע הבא אחה״צ?"
Output:
{{"service_name": "פדיקור", "start_date": "{next_week_start.isoformat()}", "start_time": "16:00", "end_date": "{next_week_end.isoformat()}", "end_time": "20:00"}}

6) Input: "אפשר תור פדיקור בחמישי?"
Output:
{{"service_name": "פדיקור", "start_date": "<next Thursday date>", "start_time": null, "end_date": "<next Thursday date>", "end_time": null}}
(Where "<next Thursday date>" is the next occurrence of Thursday from Today, preferably within NEXT 7 DAYS.)
""".strip()
