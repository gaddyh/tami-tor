# workflows/client_session/flow_read.py
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

async def run_read(wf, seed: Dict[str, Any]) -> Dict[str, Any]:
    wf.state.step = wf.SessionStep.READ if hasattr(wf.SessionStep, "READ") else wf.SessionStep.SERVICE_PICK

    bookings = await workflow.execute_activity(
        "fetch_bookings",
        {"business_id": wf.business_id, "client_id": wf.client_id, "filters": seed},
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=DEFAULT_RETRY,
    )
    await workflow.execute_activity(
        "send_bookings_list",
        {"client_id": wf.client_id, "bookings": bookings},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )
    wf.state.step = wf.SessionStep.DONE
    return {"ok": True, "intent": "read", "count": len(bookings)}
