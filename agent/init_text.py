import json
from datetime import date, timedelta
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(".venv/.env")

client = OpenAI()

# -----------------------------
# 1) System prompt
# -----------------------------
SYSTEM_PROMPT = """
You are an assistant that bootstraps a booking request into a structured object.

Goal:
From the user’s message, infer as many fields as possible for:
- service_name: str
- start_date: str
- start_time: str
- end_date: str
- end_time: str

Allowed service_name values (closed list):
- appointment
- haircut
- hair_color
- nails
- manicure
- pedicure
- massage
- facial
- waxing
- eyebrows
- lashes
- makeup
- consultation

Hebrew → service mapping examples (non-exhaustive):
- "תור", "פגישה" → appointment
- "תספורת", "ספר" → haircut
- "צבע", "צבע לשיער" → hair_color
- "ציפורניים" → nails
- "מניקור" → manicure
- "פדיקור" → pedicure
- "עיסוי" → massage
- "טיפול פנים" → facial
- "שעווה" → waxing
- "גבות" → eyebrows
- "ריסים" → lashes
- "איפור" → makeup
- "ייעוץ", "פגישת ייעוץ" → consultation

Date extraction rules:
1) Extract first, ask later. Fill what is clear with high confidence.
2) Never hallucinate. If unclear, output null.
3) Interpret relative expressions using the provided CURRENT DATE CONTEXT (authoritative mapping).
4) Prefer ranges for vague windows (e.g., "שבוע הבא").
5) ISO date format only:
   - Date: YYYY-MM-DD
6) If the user implies a single day, set start_date and end_date to the same value.
7) Multiple mentions: choose the primary intent; if ambiguous, output null rather than guessing.

Time extraction rules:
8) Explicit times:
   - If the user specifies an exact time ("בשעה 14:00", "בשתיים", "2 בצהריים"):
     - start_time = HH:MM
     - end_time = same HH:MM unless an explicit end time or duration is given
9) Time-of-day windows (use these exact bounds):
   - "בבוקר" → start_time=08:00, end_time=12:00
   - "בצהריים" → start_time=12:00, end_time=16:00
   - "אחה״צ" / "אחר הצהריים" → start_time=16:00, end_time=20:00
   - "בערב" → start_time=18:00, end_time=22:00
10) No time guessing:
   - If the user does not mention time or a time window: start_time=null, end_time=null

Range + time window rule (important):
11) If the user provides a multi-day date range (e.g., "שבוע הבא") and also provides a time window (e.g., "אחה״צ", "בבוקר"):
   - Keep start_date and end_date as the full range
   - Apply start_time/end_time as the daily window across that range
   - Do NOT collapse the date range to a single day unless a specific day is mentioned

Output rules (STRICT):
- Output only a JSON object
- Keys must be exactly: service_name, start_date, start_time, end_date, end_time
- Use null for unknown values
- No extra text.
""".strip()


# -----------------------------
# 2) Build injected context message
#    - includes today + next 7 days mapping
#    - defines "שבוע הבא" as NEXT CALENDAR WEEK in Israel convention (Sunday–Saturday)
# -----------------------------
def build_calendar_context(current_date: date, timezone: str) -> str:
    # Hebrew weekday names
    # Python: Monday=0 ... Sunday=6
    heb_weekdays = ["יום שני", "יום שלישי", "יום רביעי", "יום חמישי", "יום שישי", "שבת", "יום ראשון"]

    def day_name(d: date) -> str:
        return heb_weekdays[d.weekday()]

    # Next 7 days (for deterministic "ביום <weekday>" resolution near-term)
    d1 = current_date + timedelta(days=1)
    d2 = current_date + timedelta(days=2)
    d3 = current_date + timedelta(days=3)
    d4 = current_date + timedelta(days=4)
    d5 = current_date + timedelta(days=5)
    d6 = current_date + timedelta(days=6)
    d7 = current_date + timedelta(days=7)

    # Define "שבוע הבא" as next calendar week Sunday–Saturday (Israel common convention)
    # Find next Sunday strictly after today
    days_until_next_sunday = (6 - current_date.weekday()) % 7
    if days_until_next_sunday == 0:
        days_until_next_sunday = 7  # ensure "next" Sunday, not today
    next_week_start = current_date + timedelta(days=days_until_next_sunday)  # Sunday
    next_week_end = next_week_start + timedelta(days=6)  # Saturday

    calendar_context_message = f"""
CURRENT DATE CONTEXT

Today is: {current_date.isoformat()}
Timezone: {timezone}

AUTHORITATIVE DAY MAPPING
- Today: {current_date.isoformat()}
- Tomorrow: {d1.isoformat()}

NEXT 7 DAYS (authoritative for near-term weekday mentions)
- {day_name(d1)}: {d1.isoformat()}
- {day_name(d2)}: {d2.isoformat()}
- {day_name(d3)}: {d3.isoformat()}
- {day_name(d4)}: {d4.isoformat()}
- {day_name(d5)}: {d5.isoformat()}
- {day_name(d6)}: {d6.isoformat()}
- {day_name(d7)}: {d7.isoformat()}

HEBREW DATE INTERPRETATION RULES
- "היום" → {current_date.isoformat()}
- "מחר" → {d1.isoformat()}
- "מחרתיים" → {d2.isoformat()}
- "בעוד X ימים" → current_date + X days
- "ביום <weekday>" → choose the next occurrence of that weekday on or after tomorrow (prefer within NEXT 7 DAYS if present)
- "שבוע הבא" → NEXT CALENDAR WEEK (Israel convention: Sunday–Saturday):
    start_date = {next_week_start.isoformat()}
    end_date   = {next_week_end.isoformat()}

RANGE HANDLING
- If a phrase implies a range (e.g., "שבוע הבא", "במהלך השבוע"):
  - start_date = earliest matching date
  - end_date = latest matching date
- Do not assume times unless explicitly stated

CONFLICT RESOLUTION
- If both a relative term and a weekday appear, prefer the more specific one
- If ambiguity remains, leave affected fields as null
""".strip()

    return calendar_context_message


# -----------------------------
# 3) Call the model
# -----------------------------
def bootstrap_calendar_event(user_text: str) -> dict:
    # Example runtime context (swap these with your real runtime values)
    current_date = date(2026, 2, 2)
    timezone = "Asia/Jerusalem"

    context_msg = build_calendar_context(current_date, timezone)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_msg},
        {"role": "user", "content": user_text},
    ]

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0,
    )

    raw = resp.choices[0].message.content.strip()
    return json.loads(raw)


if __name__ == "__main__":
    examples = [
        "אני רוצה לקבוע תור",
        "אני רוצה תור לציפורניים",
        "יש תספורת שבוע הבא",
        "יש תספורת מחר בשתיים?",
        "יש פדיקור שבוע הבא אחה״צ?",
    ]

    for text in examples:
        out = bootstrap_calendar_event(text)
        print(text)
        print(out)
        print("-" * 40)
