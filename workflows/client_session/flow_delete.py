# workflows/client_session/flow_delete.py
from __future__ import annotations
from datetime import timedelta
from typing import Dict, Any

from temporalio import workflow
from temporalio.common import RetryPolicy

DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)

async def run_delete(wf, seed: Dict[str, Any]) -> Dict[str, Any]:
    wf.state.step = wf.SessionStep.DELETE if hasattr(wf.SessionStep, "DELETE") else wf.SessionStep.SERVICE_PICK

    if seed.get("booking_id") and not getattr(wf.state.data, "booking_id", None):
        wf.state.data.booking_id = seed["booking_id"]

    if not getattr(wf.state.data, "booking_id", None):
        bookings = await workflow.execute_activity(
            "fetch_bookings",
            {"business_id": wf.business_id, "client_id": wf.client_id, "filters": seed},
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )
        await workflow.execute_activity(
            "send_bookings_list",
            {"client_id": wf.client_id, "bookings": bookings, "select_mode": "delete"},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )
        await workflow.wait_condition(lambda: wf.state.cancelled or getattr(wf.state.data, "booking_id", None) is not None)
        if wf.state.cancelled:
            return await wf.finish_cancel("delete_pick")

    wf.state.step = wf.SessionStep.CONFIRM
    wf.state.data.confirmed = None
    await workflow.execute_activity(
        "send_confirm_buttons",
        {"client_id": wf.client_id, "text": "לבטל את ההזמנה הזו?"},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )
    await wf.wait_with_fallback(
        intent="DELETE",
        step="CONFIRM",
        predicate=lambda: wf.state.cancelled or wf.state.data.confirmed is not None,
        context={},
        apply_delta=wf.apply_common_delta,
    )
    if wf.state.cancelled or wf.state.data.confirmed is False:
        return await wf.finish_cancel("delete_confirm")

    await workflow.execute_activity(
        "delete_booking",
        {"business_id": wf.business_id, "client_id": wf.client_id, "booking_id": wf.state.data.booking_id},
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=DEFAULT_RETRY,
    )
    wf.state.step = wf.SessionStep.DONE
    await workflow.execute_activity(
        "send_text",
        {"client_id": wf.client_id, "text": "בוטל ✅"},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )
    return {"ok": True, "intent": "delete", "booking_id": wf.state.data.booking_id}
