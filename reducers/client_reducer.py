from dataclasses import dataclass
from models.session_state import SessionFlow, SessionStep
from adapters.primitivies import RawMessage
from typing import Any, List, Literal, TypedDict, Union

class SendTextEffect(TypedDict):
    kind: Literal["SEND_TEXT"]
    to: Literal["client", "owner"]
    text: str

class EnqueueOwnerApprovalEffect(TypedDict):
    kind: Literal["ENQUEUE_OWNER_APPROVAL"]
    # keep it minimal: reducer emits *intent*, handler fills DB ids
    payload: dict[str, Any]

Effect = Union[SendTextEffect, EnqueueOwnerApprovalEffect]

@dataclass(frozen=True)
class ReduceResult:
    flow: SessionFlow
    step: SessionStep
    data: dict[str, Any]
    effects: list[Effect]

def reduce_session(
    *,
    flow: SessionFlow,
    step: SessionStep,
    data: dict[str, Any],
    msg: RawMessage,
) -> ReduceResult:
    """
    Pure transition function.
    - Never touches DB
    - Never calls external APIs
    - Deterministic: same input => same output
    """
    # TODO: Implement the actual reduction logic
    return ReduceResult(
        flow=flow,
        step=step,
        data=data,
        effects=[],
    )
