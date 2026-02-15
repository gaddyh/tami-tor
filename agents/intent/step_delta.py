# agents/intent/step_delta.py

from __future__ import annotations
from typing import Any, Dict

from temporalio import activity


@activity.defn
async def llm_step_extract(intent: str, step: str, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stub that tries to interpret simple confirmations.
    """
    m = (text or "").strip().lower()
    if step == "CONFIRM":
        if m in {"yes", "y", "כן", "יאללה", "אשר", "מאשר"}:
            return {"confirmed": True}
        if m in {"no", "n", "לא", "בטל"}:
            return {"confirmed": False}
    return {}
