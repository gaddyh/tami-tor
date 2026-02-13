from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any
from temporalio import activity

from models.service import Service

@dataclass
class Slot:
    id: str
    start_iso: str
    end_iso: str


@activity.defn
async def load_services(dict: Dict[str, Any]) -> List[Service]:
    # stub: replace with DB
    business_id = dict["business_id"]
    return [
        Service(id="haircut", name="Haircut", duration_min=30, price=25.0),
        Service(id="beard", name="Beard", duration_min=15, price=15.0),
    ]


@activity.defn
async def compute_slots(payload: Dict[str, Any]) -> List[Slot]:
    # stub: replace with Google availability
    service_id = payload["service_id"]
    return [
        Slot(id=f"{service_id}-slot-1", start_iso="2026-02-07T10:00:00+02:00", end_iso="2026-02-07T10:30:00+02:00"),
        Slot(id=f"{service_id}-slot-2", start_iso="2026-02-07T11:00:00+02:00", end_iso="2026-02-07T11:30:00+02:00"),
    ]


@activity.defn
async def send_text(payload: Dict[str, Any]) -> None:
    # stub: replace with WhatsApp Cloud API
    activity.logger.info("SEND_TEXT -> %s", payload)


@activity.defn
async def send_services_list(payload: Dict[str, Any]) -> None:
    activity.logger.info("SEND_SERVICES_LIST -> %s", payload)


@activity.defn
async def send_slots_list(payload: Dict[str, Any]) -> None:
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

