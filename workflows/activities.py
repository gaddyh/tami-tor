from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any
from temporalio import activity
from datetime import datetime, timedelta

from models.service import Service
from db.ops.business import get_services_by_business_id
from db.ops.business_provider import get_business_provider_id
from db.session_async import get_async_db

from apps.config import get_adapter_global, now_israel, get_timezone_str
from adapters.cloud_api import CloudAPIAdapter
from adapters.google.availability import get_available_slots, divide_chunked_into_slots, is_exact_start_match
from models.availability import ChunkedAvailability
from models.availability import TimeSlot
from handlers.helper import build_hebrew_slot_confirmation, create_whatsapp_list_message
from db.models.business import Business
from handlers.helper import create_whatsapp_list_message

@dataclass
class Slot:
    id: str
    start_iso: str
    end_iso: str

def services_list_payload(rows) -> Dict[str, Any]:
    return {
        "type": "list",
        "body": {"text": "באיזה שירות תרצי לבחור?"},
        "action": {"button": "בחירה", "sections": [{"title": "שירותים זמינים", "rows": rows}]},
    }

@activity.defn
async def load_services(dict: Dict[str, Any]) -> List[Service]:
    # stub: replace with DB
    business_id = dict["business_id"]
    async with get_async_db() as db:
        return await get_services_by_business_id(db, business_id)

@activity.defn
async def compute_slots(payload: Dict[str, Any]) -> List[Slot]:
    # stub: replace with Google availability
    service_id = payload["service_id"]
    start_date = payload["start_date"] or now_israel().strftime("%Y-%m-%d")
    end_date = payload["end_date"] or (now_israel() + timedelta(days=5)).strftime("%Y-%m-%d")
    start_time = payload["start_time"] or "09:00"
    end_time = payload["end_time"] or "18:00"
    duration = payload["duration"]
    client_id = payload["client_id"]
    adapter: CloudAPIAdapter = get_adapter_global()
    
    start_dt = datetime.fromisoformat(start_date + "T" + start_time)
    end_dt = datetime.fromisoformat(end_date + "T" + end_time)
    now = start_dt or now_israel()
    end_date = end_dt or (now + timedelta(days=5))

    async with get_async_db() as db:
        provider_id = await get_business_provider_id(db, business_id=payload["business_id"])
    
    items = get_available_slots(
        user_id=provider_id,
        timezone=get_timezone_str(),
        start_date=now.isoformat(),
        end_date=end_date.isoformat(),
        duration=duration,
    )

    if len(items) == 0:
        res = await adapter.send_message(
            recipient=client_id,
            message="אין זמינות",
        )
        print("SEND_TEXT response:", res)
        activity.logger.info("SEND_TEXT -> %s", res)
        return []

    if is_exact_start_match(items, start_dt):
        chunked: ChunkedAvailability = divide_chunked_into_slots(items, chunk_size=5)
        chosen = chunked.chunks[0].slots[0]
        slot = TimeSlot.model_validate(chosen)
        payload = build_hebrew_slot_confirmation(slot)

        await adapter.send_action_buttons(
            recipient=client_id,
            message=payload,
        )
        return [slot]

    chunked: ChunkedAvailability = divide_chunked_into_slots(items, chunk_size=5)

    payload = create_whatsapp_list_message(chunked, client_id, 0)
    res = await adapter.send_dynamic_list_message(
        to_phone=client_id,
        interactive_payload=payload,
    )
    return chunked.chunks


@activity.defn
async def send_text(payload: Dict[str, Any]) -> None:
    client_id = payload["client_id"]
    text = payload["text"]
    adapter: CloudAPIAdapter = get_adapter_global()
    res = await adapter.send_message(
        recipient=client_id,
        message=text,
    )
    print("SEND_TEXT response:", res)
    activity.logger.info("SEND_TEXT -> %s", res)


@activity.defn
async def send_services_list(payload: Dict[str, Any]) -> None:
    services = payload["services"]
    client_id = payload["client_id"]
    rows = [{"id": f"svc:{s['id']}", "title": s["name"]} for s in services]
    adapter: CloudAPIAdapter = get_adapter_global()
    res = await adapter.send_dynamic_list_message(
        to_phone=client_id,
        interactive_payload=services_list_payload(rows),
    )
    print("SEND_SERVICES_LIST response:", res)
    activity.logger.info("SEND_SERVICES_LIST -> %s", res)


@activity.defn
async def send_slots_list(payload: Dict[str, Any]) -> None:
    create_whatsapp_list_message(payload["slots"], payload["client_id"], 0)
    activity.logger.info("SEND_SLOTS_LIST -> %s", payload)


@activity.defn
async def send_confirm_buttons(payload: Dict[str, Any]) -> None:
    activity.logger.info("SEND_CONFIRM_BUTTONS -> %s", payload)


@activity.defn
async def create_booking(payload: Dict[str, Any]) -> str:
    # stub: replace with DB + GCal create; return booking_id
    return "bk_12345"

@activity.defn
async def transcribe_audio(payload: Dict[str, Any]) -> str:
    # stub: replace with Google Cloud Speech-to-Text; return text
    return "hello world"

