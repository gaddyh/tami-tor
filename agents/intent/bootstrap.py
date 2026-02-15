# agents/intent/bootstrap.py
from __future__ import annotations

import os
import re
from enum import StrEnum
from typing import Any, Dict, Optional, List

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from temporalio import activity

from runtime.events import now_israel
from agents.init_text import build_system_prompt  # <-- YOUR prompt builder
from models.service import Service

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
    OTHER = "OTHER"


class ExtractBootstrapInput(BaseModel):
    intent: str
    text: str
    services: list[dict] = Field(default_factory=list)
    business_id: str
    client_id: str


# -------- output schemas --------
class BookingBootstrap(BaseModel):
    service_name: str | None = None
    start_date: str | None = None  # YYYY-MM-DD
    start_time: str | None = None  # HH:MM
    end_date: str | None = None    # YYYY-MM-DD
    end_time: str | None = None    # HH:MM


class ReadBootstrap(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


class DeleteBootstrap(BaseModel):
    booking_id: str | None = None


class UpdatePatch(BaseModel):
    service_name: str | None = None
    start_date: str | None = None
    start_time: str | None = None
    end_date: str | None = None
    end_time: str | None = None


class UpdateBootstrap(BaseModel):
    booking_id: str | None = None
    patch: UpdatePatch = Field(default_factory=UpdatePatch)


# -------- heuristics --------
def _extract_booking_id(message_lower: str) -> Optional[str]:
    tokens = message_lower.replace("#", " ").replace(":", " ").split()
    keys = {"booking", "id", "הזמנה", "מספר", "מס'", "מספרהזמנה"}
    for i, tok in enumerate(tokens[:-1]):
        if tok in keys:
            nxt = tokens[i + 1].strip()
            if nxt:
                return nxt
    m = re.search(r"\b(?:booking|id)\s*=\s*([A-Za-z0-9_-]{3,64})\b", message_lower)
    if m:
        return m.group(1)
    return None


def _to_services(services_dicts: list[dict]) -> List[Service]:
    """
    Convert list[dict] -> list[Service] for your prompt builder.
    Keep it tolerant: missing fields become None/defaults.
    """
    out: List[Service] = []
    for d in services_dicts or []:
        try:
            # adjust fields if your Service model differs
            out.append(
                Service(
                    id=str(d.get("id") or ""),
                    name=str(d.get("name") or ""),
                    duration_min=int(d["duration_min"]) if d.get("duration_min") is not None else None,
                    price=d.get("price"),
                    is_active=bool(d.get("is_active", True)),
                )
            )
        except Exception:
            # If a single service is malformed, skip it (don’t crash).
            continue
    return out


def _system_prompt_for_booking(services: List[Service]) -> str:
    return build_system_prompt(
        current_datetime=now_israel(),
        timezone="Asia/Jerusalem",
        services=services,
    )


@activity.defn
async def llm_extract_bootstrap(inp: ExtractBootstrapInput) -> Dict[str, Any]:
    intent_raw = (inp.intent or "").upper()
    intent: Intent = Intent(intent_raw) if intent_raw in Intent.__members__ else Intent.OTHER

    text = (inp.text or "").strip()
    services = _to_services(inp.services)

    # DELETE/UPDATE need booking id heuristic regardless
    booking_id = _extract_booking_id(text)

    # No LLM? return safe heuristic-only payloads
    if not os.getenv("OPENAI_API_KEY"):
        return _fallback_without_llm(intent, booking_id)

    client = _get_client()
    model = os.getenv("BOOTSTRAP_EXTRACT_MODEL", "gpt-5.2")

    # CREATE/UPDATE can reuse your booking bootstrap prompt
    if intent in {Intent.CREATE, Intent.UPDATE}:
        try:
            system_prompt = _system_prompt_for_booking(services)

            resp = client.responses.parse(
                model=model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                text_format=BookingBootstrap,
            )
            boot: BookingBootstrap = resp.output_parsed

            if intent == Intent.CREATE:
                return {"intent": "CREATE", "payload": boot.model_dump(mode="json")}

            # UPDATE: wrap into patch, keep booking_id heuristic
            patch = UpdatePatch(**boot.model_dump())
            out = UpdateBootstrap(booking_id=booking_id, patch=patch)
            return {"intent": "UPDATE", "payload": out.model_dump(mode="json")}

        except Exception as e:
            activity.logger.warning(f"llm_extract_bootstrap booking parse failed: {e}")
            return _fallback_without_llm(intent, booking_id)

    # READ: keep simple (dates only). If you want, you can later add a similar prompt.
    if intent == Intent.READ:
        return {"intent": "READ", "payload": ReadBootstrap().model_dump(mode="json")}

    if intent == Intent.DELETE:
        return {"intent": "DELETE", "payload": DeleteBootstrap(booking_id=booking_id).model_dump(mode="json")}

    if intent == Intent.HELP:
        return {"intent": "HELP", "payload": None}

    return {"intent": "OTHER", "payload": None}


def _fallback_without_llm(intent: Intent, booking_id: Optional[str]) -> Dict[str, Any]:
    if intent == Intent.CREATE:
        return {"intent": "CREATE", "payload": BookingBootstrap().model_dump(mode="json")}

    if intent == Intent.UPDATE:
        return {
            "intent": "UPDATE",
            "payload": UpdateBootstrap(booking_id=booking_id, patch=UpdatePatch()).model_dump(mode="json"),
        }

    if intent == Intent.READ:
        return {"intent": "READ", "payload": ReadBootstrap().model_dump(mode="json")}

    if intent == Intent.DELETE:
        return {"intent": "DELETE", "payload": DeleteBootstrap(booking_id=booking_id).model_dump(mode="json")}

    if intent == Intent.HELP:
        return {"intent": "HELP", "payload": None}

    return {"intent": "OTHER", "payload": None}


if __name__ == "__main__":
    import asyncio
    import time as pytime

    async def _run():
        services = [
            {"id": "1", "name": "פדיקור", "duration_min": 60, "price": 100, "is_active": True},
            {"id": "2", "name": "מניקור", "duration_min": 60, "price": 120, "is_active": True},
            {"id": "3", "name": "תספורת", "duration_min": 30, "price": 80, "is_active": True},
        ]

        cases = [
            ("CREATE", "אפשר תור לפדיקור ביום חמישי ב-10:30?", services),
            ("DELETE", "תבטל הזמנה 7H2K9", services),
            ("UPDATE", "אני רוצה לשנות הזמנה 7H2K9 לשישי ב-12:00", services),
            ("UPDATE", "שנה לי את התספורת לרביעי", services),
            ("HELP", "היי", services),
        ]

        for intent, text, svcs in cases:
            start = pytime.perf_counter()
            out = await llm_extract_bootstrap(
                ExtractBootstrapInput(
                    intent=intent,
                    text=text,
                    services=svcs,
                    business_id="demo_biz",
                    client_id="demo_client",
                )
            )
            elapsed = pytime.perf_counter() - start
            print(f"\nIntent: {intent}")
            print(f"Text:   {text}")
            print(f"Out:    {out}")
            print(f"Took:   {elapsed:.2f}s")

    asyncio.run(_run())
