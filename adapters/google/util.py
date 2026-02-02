from datetime import datetime, timezone

# Map loose weekday strings → RFC5545 2-letter codes
_WEEKDAY_MAP = {
    "mo": "MO", "mon": "MO",
    "tu": "TU", "tue": "TU", "tues": "TU",
    "we": "WE", "wed": "WE",
    "th": "TH", "thu": "TH", "thur": "TH", "thurs": "TH",
    "fr": "FR", "fri": "FR",
    "sa": "SA", "sat": "SA",
    "su": "SU", "sun": "SU",
}

_FREQ_MAP = {
    "daily": "DAILY",
    "weekly": "WEEKLY",
    "monthly": "MONTHLY",
    "yearly": "YEARLY",
}

def _iso_to_rfc5545_z(dt_str: str) -> str:
    """
    ISO8601 → RFC5545 UTC 'YYYYMMDDTHHMMSSZ'.
    Accepts 'YYYY-MM-DD' (treated as 00:00Z), '...Z', or offset forms.
    """
    s = dt_str.strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        # Date only
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    else:
        s = s.replace("Z", "+00:00") if s.endswith("Z") else s
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")

def _normalize_byday(by_day: list[str]) -> list[str]:
    out = []
    for d in by_day:
        key = d.strip().lower()
        # Support things like "MO", "mo", "Mon"
        if key in _WEEKDAY_MAP:
            out.append(_WEEKDAY_MAP[key])
        else:
            # If already valid 2-letter code, keep upper
            if len(d) == 2 and d.upper() in _WEEKDAY_MAP.values():
                out.append(d.upper())
            else:
                raise ValueError(f"Invalid BYDAY value: {d}")
    return out
