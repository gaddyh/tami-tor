# agents/intent/core.py
from __future__ import annotations

from typing import Any, Dict
from pydantic import BaseModel
from temporalio import activity


class RouteIntentInput(BaseModel):
    text: str
    business_id: str
    client_id: str


@activity.defn
async def llm_route_intent(inp: RouteIntentInput) -> Dict[str, Any]:
    m = (inp.text or "").strip().lower()

    # explicit intents win
    if any(w in m for w in ["לבטל", "בטל", "cancel"]):
        return {"intent": "DELETE", "confidence": 0.95}
    if any(w in m for w in ["לשנות", "שנה", "update"]):
        return {"intent": "UPDATE", "confidence": 0.95}
    if any(w in m for w in ["להציג", "תורים", "show", "list"]):
        return {"intent": "READ", "confidence": 0.95}

    # default: booking creation (WhatsApp booking bot bias)
    return {"intent": "CREATE", "confidence": 0.55}
