# agents/intent/core.py
from __future__ import annotations

import os
from enum import StrEnum
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from temporalio import activity

load_dotenv(".venv/.env")

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


class Intent(StrEnum):
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    HELP = "HELP"
    UNKNOWN = "UNKNOWN"
    OTHER = "OTHER"


class RouteIntentInput(BaseModel):
    text: str
    business_id: str
    client_id: str


class RouteIntentResult(BaseModel):
    intent: Intent = Field(..., description="The chosen intent")
    confidence: float = Field(..., ge=0.0, le=1.0, description="0..1 confidence")
    # Optional but useful for debugging/analytics
    language: str | None = Field(None, description="he/en/mixed/other")
    matched_keywords: list[str] = Field(default_factory=list)


_KEYWORDS = {
    Intent.DELETE: ["לבטל", "בטל", "ביטול", "cancel", "cancellation", "delete"],
    Intent.UPDATE: ["לשנות", "שנה", "לעדכן", "עדכון", "update", "change", "reschedule", "דחייה", "להזיז"],
    Intent.READ: ["להציג", "תורים", "להראות", "רשימה", "מה קיים", "show", "list", "my appointments", "appointments"],
}

_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "yo",
    "sup",
    "שלום",
    "היי",
    "הי",
    "מה קורה",
    "מה נשמע",
    "ערב טוב",
    "בוקר טוב",
    "צהריים טובים",
}


def _looks_like_greeting(m: str) -> bool:
    mm = (m or "").strip().lower()
    if not mm:
        return True
    if mm in _GREETINGS:
        return True
    # super-short pings like "hi", "yo", "?" etc.
    if len(mm) <= 3:
        return True
    return False


def _keyword_route(m: str) -> RouteIntentResult | None:
    hits: list[tuple[Intent, str]] = []
    for intent, words in _KEYWORDS.items():
        for w in words:
            if w in m:
                hits.append((intent, w))

    if not hits:
        return None

    # explicit wins: priority order
    priority = [Intent.DELETE, Intent.UPDATE, Intent.READ]
    for p in priority:
        for intent, w in hits:
            if intent == p:
                return RouteIntentResult(
                    intent=p,
                    confidence=0.95,
                    language=None,
                    matched_keywords=[w],
                )

    return None


def _system_prompt() -> str:
    return (
        "You are an intent router for a WhatsApp booking bot.\n"
        "Classify the user's message into exactly ONE intent:\n"
        "- CREATE: user wants to book / make an appointment / ask for availability.\n"
        "- READ: user wants to see existing appointments / list / status.\n"
        "- UPDATE: user wants to change/reschedule/update an existing appointment.\n"
        "- DELETE: user wants to cancel/delete an existing appointment.\n"
        "- UNKNOWN: cannot tell.\n"
        "Rules:\n"
        "1) If the user explicitly asks to cancel => DELETE.\n"
        "2) If the user explicitly asks to change/reschedule => UPDATE.\n"
        "3) If the user asks to show/list existing appointments => READ.\n"
        "4) Otherwise default to CREATE.\n"
        "Return a JSON object matching the provided schema.\n"
        "Keep confidence 0..1. Use ~0.55 for default CREATE when vague.\n"
        "Support Hebrew and English.\n"
    )


@activity.defn
async def llm_route_intent(inp: RouteIntentInput) -> Dict[str, Any]:
    text = (inp.text or "").strip()
    m = text.lower()

    # 1) cheap greeting detection (avoid accidental booking flows + LLM calls)
    if _looks_like_greeting(m):
        return RouteIntentResult(intent=Intent.CREATE, confidence=0.90).model_dump(mode="json")

    # 2) fast explicit route (cheap + reliable)
    kw = _keyword_route(m)
    if kw is not None:
        return kw.model_dump(mode="json")

    # 3) LLM route
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Safe fallback if env missing (don’t crash the workflow)
        return RouteIntentResult(intent=Intent.CREATE, confidence=0.55).model_dump(mode="json")

    client = _get_client()
    model = os.getenv("INTENT_ROUTER_MODEL", "gpt-5.2")

    user_prompt = (
        f"business_id={inp.business_id}\n"
        f"client_id={inp.client_id}\n"
        f"text={text}\n"
    )

    try:
        resp = client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            text_format=RouteIntentResult,
        )
        parsed: RouteIntentResult = resp.output_parsed

        # Guardrails: avoid UNKNOWN making the bot weird
        if parsed.intent == Intent.UNKNOWN:
            parsed = RouteIntentResult(intent=Intent.CREATE, confidence=min(parsed.confidence, 0.75))

        return parsed.model_dump(mode="json")

    except Exception as e:
        # Don’t fail the whole session on transient LLM issues.
        activity.logger.warning(f"llm_route_intent failed, fallback to CREATE: {e}")
        return RouteIntentResult(intent=Intent.CREATE, confidence=0.75).model_dump(mode="json")


if __name__ == "__main__":
    import asyncio
    import time as pytime

    async def _run():
        samples = [
            "אפשר תור לפדיקור ביום חמישי?",
            "תבטל לי את התור",
            "אני רוצה לשנות לשישי",
            "תראה לי את כל התורים שלי",
            "hi",
            "?",
            "שלום",
        ]

        for s in samples:
            start = pytime.perf_counter()

            res = await llm_route_intent(
                RouteIntentInput(
                    text=s,
                    business_id="demo_biz",
                    client_id="demo_client",
                )
            )

            elapsed = pytime.perf_counter() - start
            print(f"\nInput: {s}")
            print(f"Output: {res}")
            print(f"Took: {elapsed:.2f}s")

    asyncio.run(_run())
