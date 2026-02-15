# agents/intent/bootstrap.py
from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from temporalio import activity


class ExtractBootstrapInput(BaseModel):
    intent: str
    text: str
    services: list[dict] = Field(default_factory=list)
    business_id: str
    client_id: str


@activity.defn
async def llm_extract_bootstrap(inp: ExtractBootstrapInput) -> Dict[str, Any]:
    intent = (inp.intent or "").upper()
    m = (inp.text or "").strip().lower()
    services = inp.services or []

    if intent == "CREATE":
        service_name = _guess_service_name(m, services)
        return {
            "intent": "CREATE",
            "payload": {
                "service_name": service_name,
                "start_date": None,
                "end_date": None,
                "start_time": None,
                "end_time": None,
            },
        }

    if intent == "READ":
        return {"intent": "READ", "payload": {"start_date": None, "end_date": None}}

    if intent == "DELETE":
        return {"intent": "DELETE", "payload": {"booking_id": _extract_booking_id(m)}}

    if intent == "UPDATE":
        booking_id = _extract_booking_id(m)
        service_name = _guess_service_name(m, services)
        return {
            "intent": "UPDATE",
            "payload": {
                "booking_id": booking_id,
                "patch": {
                    "service_name": service_name,
                    "start_date": None,
                    "end_date": None,
                    "start_time": None,
                    "end_time": None,
                },
            },
        }

    return {"intent": "OTHER", "payload": None}


def _guess_service_name(message_lower: str, services: list[dict]) -> Optional[str]:
    """
    Returns the first service whose name (or common aliases) appears in the message.
    """
    # direct match on service name
    for s in services:
        name = (s.get("name") or "").strip()
        if name and name.lower() in message_lower:
            return name

    # very small alias map (extend as needed)
    aliases = {
        "haircut": {"haircut", "trim", "תספורת"},
        "beard": {"beard", "זקן"},
    }

    for s in services:
        name = (s.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        for alias_set in aliases.values():
            if any(a in message_lower for a in alias_set):
                return name

    return None


def _extract_booking_id(message_lower: str) -> Optional[str]:
    """
    Naive: looks for tokens like 'booking', 'id', 'הזמנה' and grabs next token.
    """
    tokens = message_lower.replace("#", " ").replace(":", " ").split()
    keys = {"booking", "id", "הזמנה", "מספר"}
    for i, tok in enumerate(tokens[:-1]):
        if tok in keys:
            nxt = tokens[i + 1].strip()
            if nxt:
                return nxt
    return None
