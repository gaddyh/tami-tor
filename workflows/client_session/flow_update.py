# workflows/client_session/flow_update.py
from __future__ import annotations
from datetime import timedelta
from typing import Dict, Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from workflows.client_session.utils import find_service_id_by_name

DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)

async def run_update(wf, services, seed: Dict[str, Any]) -> Dict[str, Any]:
    wf.state.step = wf.SessionStep.UPDATE if hasattr(wf.SessionStep, "UPDATE") else wf.SessionStep.SERVICE_PICK

    if seed.get("booking_id") and not getattr(wf.state.data, "booking_id", None):
        wf.state.data.booking_id = seed["booking_id"]

    if not getattr(wf.state.data, "booking_id", None):
        bookings = await workflow.execute_activity(
            "fetch_bookings",
            {"business_id": wf.business_id, "client_id": wf.client_id, "filters": seed.get("target") or seed},
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )
        await workflow.execute_activity(
            "send_bookings_list",
            {"client_id": wf.client_id, "bookings": bookings, "select_mode": "update"},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )
        await workflow.wait_condition(lambda: wf.state.cancelled or getattr(wf.state.data, "booking_id", None) is not None)
        if wf.state.cancelled:
            return await wf.finish_cancel("update_pick")

    patch = seed.get("patch") or {}
    new_service_id = None
    if patch.get("service_name"):
        new_service_id = find_service_id_by_name(services, patch["service_name"])

    needs_new_slot = any(patch.get(k) is not None for k in ("start_date", "end_date", "start_time", "end_time", "service_name"))
    new_slot_id = None
    if needs_new_slot:
        await workflow.execute_activity(
            "send_text",
            {"client_id": wf.client_id, "text": "מחשב זמינות לשינוי..."},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )
        slots = await workflow.execute_activity(
            "compute_slots",
            {
                "business_id": wf.business_id,
                "service_id": new_service_id,
                "start_date": patch.get("start_date"),
                "end_date": patch.get("end_date"),
                "start_time": patch.get("start_time"),
                "end_time": patch.get("end_time"),
            },
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )
        wf.state.data.chosen_slot_id = None
        await workflow.execute_activity(
            "send_slots_list",
            {"client_id": wf.client_id, "slots": slots},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )
        await workflow.wait_condition(lambda: wf.state.cancelled or wf.state.data.chosen_slot_id is not None)
        if wf.state.cancelled:
            return await wf.finish_cancel("update_slots_pick")
        new_slot_id = wf.state.data.chosen_slot_id

    wf.state.step = wf.SessionStep.CONFIRM
    wf.state.data.confirmed = None
    await workflow.execute_activity(
        "send_confirm_buttons",
        {"client_id": wf.client_id, "text": "לאשר שינוי?"},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )
    await wf.wait_with_fallback(
        intent="UPDATE",
        step="CONFIRM",
        predicate=lambda: wf.state.cancelled or wf.state.data.confirmed is not None,
        context={},
        apply_delta=wf.apply_common_delta,
    )
    if wf.state.cancelled or wf.state.data.confirmed is False:
        return await wf.finish_cancel("update_confirm")

    await workflow.execute_activity(
        "update_booking",
        {
            "business_id": wf.business_id,
            "client_id": wf.client_id,
            "booking_id": wf.state.data.booking_id,
            "patch": patch,
            "service_id": new_service_id,
            "slot_id": new_slot_id,
        },
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=DEFAULT_RETRY,
    )
    wf.state.step = wf.SessionStep.DONE
    await workflow.execute_activity(
        "send_text",
        {"client_id": wf.client_id, "text": "עודכן ✅"},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )
    return {"ok": True, "intent": "update", "booking_id": wf.state.data.booking_id}
