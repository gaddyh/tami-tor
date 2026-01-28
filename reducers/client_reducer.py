from dataclasses import dataclass
from handlers.utility import build_service_rows
from models.session_state import SessionFlow, SessionStep
from adapters.primitivies import RawMessage
from typing import Any, List, Literal, TypedDict, Union

class ListRow(TypedDict):
    id: str          # payload you get back in list_reply.id
    title: str
    description: str | None


from typing import Any, Literal, TypedDict

class SendServiceListEffect(TypedDict):
    kind: Literal["SEND_SERVICE_LIST"]
    to: Literal["client"]
    rows: list[dict[str, Any]]  # rows = [{"id": "...", "title": "..."}]

class SendSlotsListEffect(TypedDict):
    kind: Literal["SEND_SLOTS_LIST"]
    to: Literal["client"]
    rows: list[dict[str, Any]]

class SendConfirmButtonsEffect(TypedDict):
    kind: Literal["SEND_CONFIRM_BUTTONS"]
    to: Literal["client"]
    body: str
    buttons: list[dict[str, str]]  # [{"id":"yes","title":"כן"}, ...]

class SendTextEffect(TypedDict):
    kind: Literal["SEND_TEXT"]
    to: Literal["client", "owner"]
    text: str

class EnqueueOwnerApprovalEffect(TypedDict):
    kind: Literal["ENQUEUE_OWNER_APPROVAL"]
    # keep it minimal: reducer emits *intent*, handler fills DB ids
    payload: dict[str, Any]

Effect = Union[SendTextEffect, EnqueueOwnerApprovalEffect, SendConfirmButtonsEffect, SendServiceListEffect, SendSlotsListEffect]

@dataclass(frozen=True)
class ReduceResult:
    flow: SessionFlow
    step: SessionStep
    data: dict[str, Any]
    effects: list[Effect]

def reduce_session(*, flow: SessionFlow, step: SessionStep, data: dict[str, Any], msg: RawMessage, ctx: dict[str, Any]) -> ReduceResult:
    d = dict(data or {})
    effects: list[Effect] = []

    if flow == SessionFlow.CLIENT_BOOKING:
        if step == SessionStep.INIT:
            services = ctx.get("services") or []

            if not services:
                effects.append({"kind": "SEND_TEXT", "to": "client", "text": "אין שירותים זמינים כרגע."})
                return ReduceResult(flow=flow, step=SessionStep.DONE, data=data, effects=effects)

            effects.append({"kind": "SEND_SERVICE_LIST", "to": "client", "rows": build_service_rows(services)})
            return ReduceResult(flow=flow, step=SessionStep.SERVICE_PICK, data=data, effects=effects)


        if step == SessionStep.SERVICE_PICK:
            # later: extract service intent from msg
            # for now: just echo / placeholder
            effects.append({"kind": "SEND_TEXT", "to": "client", "text": "Got it. Now pick a time slot."})
            return ReduceResult(flow=flow, step=SessionStep.SLOTS_PICK, data=d, effects=effects)

        if step == SessionStep.SLOTS_PICK:
            effects.append({"kind": "SEND_TEXT", "to": "client", "text": "Confirm? (yes/no)"})
            return ReduceResult(flow=flow, step=SessionStep.CONFIRM, data=d, effects=effects)

        if step == SessionStep.CONFIRM:
            # On confirm: finish client flow + trigger owner flow
            effects.append({"kind": "SEND_TEXT", "to": "client", "text": "Thanks. Sent to the owner for approval."})
            effects.append({"kind": "ENQUEUE_OWNER_APPROVAL", "payload": {"summary": d}})
            return ReduceResult(flow=flow, step=SessionStep.DONE, data=d, effects=effects)

    # Default fallback: reset safely
    effects.append({"kind": "SEND_TEXT", "to": "client", "text": "Let’s start over. What service do you need?"})
    return ReduceResult(flow=SessionFlow.CLIENT_BOOKING, step=SessionStep.SERVICE_PICK, data={}, effects=effects)
