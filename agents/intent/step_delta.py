# agents/intent/step_delta.py
from __future__ import annotations

from typing import Any, Dict
from pydantic import BaseModel, Field
from temporalio import activity


class StepExtractInput(BaseModel):
    intent: str
    step: str
    text: str
    context: Dict[str, Any] = Field(default_factory=dict)


@activity.defn
async def llm_step_extract(inp: StepExtractInput) -> Dict[str, Any]:
    m = (inp.text or "").strip().lower()
    step = (inp.step or "").upper()

    if step == "CONFIRM":
        if m in {"yes", "y", "כן", "יאללה", "אשר", "מאשר"}:
            return {"confirmed": True}
        if m in {"no", "n", "לא", "בטל"}:
            return {"confirmed": False}
    return {}
