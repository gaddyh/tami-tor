# workflows/client_session/flow_create.py
from __future__ import annotations
from datetime import timedelta
from typing import Any, Dict

from temporalio import workflow
from temporalio.common import RetryPolicy

from workflows.client_session.router import step_delta
from workflows.client_session.utils import find_service_id_by_name

DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)

async def run_create(wf, services: list[Any], seed: Dict[str, Any]) -> Dict[str, Any]:
    wf.state.step = wf.SessionStep.SERVICE_PICK

    # seed service
    if seed.get("service_name") and not wf.state.data.service_id:
        sid = find_service_id_by_name(services, seed["service_name"])
        if sid:
            wf.state.data.service_id = sid

    # optional constraints
    for k in ("start_date", "end_date", "start_time", "end_time"):
        if hasattr(wf.state.data, k) and seed.get(k) is not None:
            setattr(wf.state.data, k, seed.get(k))

    if not wf.state.data.service_id:
        await workflow.execute_activity(
            "send_services_list",
            {"client_id": wf.client_id, "services": services},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )
        await wf.wait_with_fallback(
            intent="CREATE",
            step="SERVICE_PICK",
            predicate=lambda: wf.state.cancelled or wf.state.data.service_id is not None,
            context={"services": services},
            apply_delta=lambda d: _apply_create_delta(wf, services, d),
        )
        if wf.state.cancelled:
            return await wf.finish_cancel("service_pick")
    
    service_name = next((s["name"] for s in services if s["id"] == wf.state.data.service_id), None)
    
    await workflow.execute_activity(
        "send_text",
        {"client_id": wf.client_id, "text": "מחשב זמינות..."},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )

    wf.state.step = wf.SessionStep.SLOTS_PICK
    service_id = wf.state.data.service_id

    if service_id.startswith("svc:"):
        service_id = service_id.removeprefix("svc:")

    duration = next(
        (s["duration_min"] for s in services if s["id"] == service_id),
        None,
    )

    chunked = await workflow.execute_activity(
        "compute_slots",
        {
            "business_id": wf.business_id,
            "service_id": service_id,
            "start_date": getattr(wf.state.data, "start_date", None),
            "end_date": getattr(wf.state.data, "end_date", None),
            "start_time": getattr(wf.state.data, "start_time", None),
            "end_time": getattr(wf.state.data, "end_time", None),
            "duration": duration,
            "client_id": wf.client_id,
        },
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=DEFAULT_RETRY,
    )

    wf.state.data.chunked = chunked

    await workflow.execute_activity(
        "send_slots_list",
        {"client_id": wf.client_id, "chunked": chunked, "index": 0},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )

    await wf.wait_with_fallback(
        intent="CREATE",
        step="SLOTS_PICK",
        predicate=lambda: wf.state.cancelled or wf.state.data.chosen_slot_id is not None,
        context={"slots": chunked},
        apply_delta=lambda d: _apply_common_confirm(wf, d),
    )
    if wf.state.cancelled:
        return await wf.finish_cancel("slots_pick")

    wf.state.step = wf.SessionStep.CONFIRM
    #wf.state.data.confirmed = None
    await workflow.execute_activity(
        "send_confirm_buttons",
        {"client_id": wf.client_id, "service_name": service_name, "slot": wf.state.data.chosen_slot},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )

    await wf.wait_with_fallback(
        intent="CREATE",
        step="CONFIRM",
        predicate=lambda: wf.state.cancelled or wf.state.data.confirmed,
        context={},
        apply_delta=lambda d: _apply_common_confirm(wf, d),
    )
    if wf.state.cancelled or not wf.state.data.confirmed:
        return await wf.finish_cancel("confirm")

    booking_id = await workflow.execute_activity(
        "create_booking",
        {
            "business_id": wf.business_id,
            "client_id": wf.client_id,
            "service_id": service_id,
            "slot": wf.state.data.chosen_slot,
            "service_name": service_name,
        },
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=DEFAULT_RETRY,
    )

    wf.state.step = wf.SessionStep.DONE
    await workflow.execute_activity(
        "send_text",
        {"client_id": wf.client_id, "text": f"אושר ✅ הזמנה נוצרה: {booking_id}"},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )
    return {"ok": True, "intent": "create", "booking_id": booking_id}

def _apply_create_delta(wf, services: list[Any], d: Dict[str, Any]) -> None:
    if not d:
        return
    if d.get("service_name") and not wf.state.data.service_id:
        sid = find_service_id_by_name(services, d["service_name"])
        if sid:
            wf.state.data.service_id = sid
    _apply_common_confirm(wf, d)

def _apply_common_confirm(wf, d: Dict[str, Any]) -> None:
    if not d:
        return
    if "confirmed" in d and not wf.state.data.confirmed:
        wf.state.data.confirmed = bool(d["confirmed"])
