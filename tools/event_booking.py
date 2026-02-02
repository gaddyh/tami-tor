from __future__ import annotations
from typing import Any, Optional, Literal, List, Dict
from observability.obs import span_attrs, mark_error, instrument_io
from models.calendar_event import EventItem, ProcessedEventResult
from adapters.google.process_event import _process_event

def summarize(result: dict):
    return result

def redact(event: EventItem):
    return event

@instrument_io(
    name="tool.create_event",
    meta={"agent": "tami", "operation": "tool", "tool": "create_event", "schema": "EventItem.v1"},
    input_fn=lambda user_id, event: {
        "user_id": user_id,
        # ↓ serialize Pydantic model for the instrumentation layer
        "event": (event.model_dump() if hasattr(event, "model_dump")
                  else event.dict() if hasattr(event, "dict")
                  else event)
    },
    output_fn=summarize,
    redact=True,
)
def create_event(user_id: str, event: EventItem):
    with span_attrs("tool.create_event", agent="tami", operation="tool", tool="create_event") as s:
        # ↓ serialize before redaction/logging to avoid .items() on a model
        _event_dict = (event.model_dump() if hasattr(event, "model_dump")
                       else event.dict() if hasattr(event, "dict")
                       else event)
        s.update(input={"args": redact(_event_dict)})
        try:
            out = _process_event(user_id, event)
            s.update(output=summarize(out))
            return out
        except Exception as e:
            mark_error(e, kind="ToolError.process_event", span=s)
            raise
