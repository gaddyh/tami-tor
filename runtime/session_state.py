from __future__ import annotations

from typing import Any, Tuple

from models.session_state import (
    SessionFlow,
    SessionStep,
    DEFAULT_FLOW,
    DEFAULT_STEP,
    DEFAULT_VERSION,
)


def parse_session_state(state_json: Any) -> tuple[SessionFlow, SessionStep, dict[str, Any]]:
    """
    Tolerant decode of Session.state_json into (flow, step, data).
    If state_json is missing/invalid, returns defaults.
    """
    if not isinstance(state_json, dict):
        return DEFAULT_FLOW, DEFAULT_STEP, {}

    # version is optional for now (kept for future migrations)
    v = state_json.get("v")
    if isinstance(v, int) and v > 0:
        _ = v  # reserved

    flow_raw = state_json.get("flow")
    step_raw = state_json.get("step")
    data_raw = state_json.get("data")

    # flow
    try:
        flow = SessionFlow(flow_raw) if flow_raw else DEFAULT_FLOW
    except Exception:
        flow = DEFAULT_FLOW

    # step
    try:
        step = SessionStep(step_raw) if step_raw else DEFAULT_STEP
    except Exception:
        step = DEFAULT_STEP

    # data
    data: dict[str, Any] = data_raw if isinstance(data_raw, dict) else {}

    return flow, step, data


def dump_session_state(flow: SessionFlow, step: SessionStep, data: dict[str, Any]) -> dict[str, Any]:
    """
    Encode back to JSON for storage.
    """
    return {
        "v": DEFAULT_VERSION,
        "flow": flow.value,
        "step": step.value,
        "data": data or {},
    }
