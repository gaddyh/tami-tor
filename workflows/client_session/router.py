# workflows/client_session/router.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict

from temporalio import workflow
from temporalio.common import RetryPolicy

from models.llm_bootstrap import RouterResult, BookingBootstrap
from models.service import Service

DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)


async def route_intent(text: str, business_id: str, client_id: str) -> RouterResult:
    raw = await workflow.execute_activity(
        "llm_route_intent",
        {"text": text, "business_id": business_id, "client_id": client_id},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )
    return RouterResult.model_validate(raw)


async def extract_bootstrap(intent: str, text: str, services: list[Service], business_id: str, client_id: str) -> BookingBootstrap:
    raw = await workflow.execute_activity(
        "llm_extract_bootstrap",
        {"intent": intent, "text": text, "services": services, "business_id": business_id, "client_id": client_id},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )
    # Expect: {"intent": "...", "payload": {...}}  (payload shape depends on intent)
    return BookingBootstrap.model_validate(raw)


async def step_delta(intent: str, step: str, text: str, context: dict) -> Dict[str, Any]:
    # keep delta as dict (fine). If you want, you can type this too later.
    return await workflow.execute_activity(
        "llm_step_extract",
        {"intent": intent, "step": step, "text": text, "context": context},
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=DEFAULT_RETRY,
    )
