# workflows/client_session/utils.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Any

from temporalio import workflow

@dataclass
class ContinuePolicy:
    every_ops: int = 50

def find_service_id_by_name(services: list[Any], service_name: str) -> Optional[str]:
    needle = service_name.strip().lower()
    for s in services:
        name = getattr(s, "name", "")
        if name and name.strip().lower() == needle:
            return getattr(s, "id", None)
    return None

def should_continue_as_new(op_seq: int, policy: ContinuePolicy) -> bool:
    try:
        if workflow.info().is_continue_as_new_suggested():
            return True
    except Exception:
        pass
    return policy.every_ops > 0 and (op_seq % policy.every_ops == 0)
