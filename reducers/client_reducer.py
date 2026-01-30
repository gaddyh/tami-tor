from dataclasses import dataclass
from handlers.utility import build_service_rows, get_list_reply_id
from models.session_state import SessionFlow, SessionStep
from adapters.primitivies import RawMessage
from typing import Any, Literal, TypedDict, Union
from reducers.helper import handle_list_response, ListResponse, NavigationResponse, SlotSelectionResponse, DisabledActionResponse, UnknownActionResponse
from models.availability import ChunkedAvailability, TimeSlot
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

from observability.obs import instrument_io

@instrument_io(
    name="reduce_session",
    meta={"operation": "reduce_session"},
    input_fn=lambda flow, step, data, msg, ctx: {
        "flow": flow.value,
        "step": step.value,
        "data": data,
        "msg": msg,
        "ctx": ctx
    },
    output_fn=lambda result: result,
    redact=True
)
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
            selected_service_id = get_list_reply_id(msg)

            if not selected_service_id:
                # user sent something else while we're expecting a list selection
                effects.append({
                    "kind": "SEND_TEXT",
                    "to": "client",
                    "text": "בחרי שירות מהרשימה בבקשה 🙂",
                })
                return ReduceResult(flow=flow, step=SessionStep.SERVICE_PICK, data=d, effects=effects)

            # validate against ctx services
            services = ctx.get("services") or []
            service = next((s for s in services if getattr(s, "id", None) == selected_service_id), None)
            if not service:
                effects.append({
                    "kind": "SEND_TEXT",
                    "to": "client",
                    "text": "לא מצאתי את השירות הזה. נסי לבחור שוב מהרשימה.",
                })
                return ReduceResult(flow=flow, step=SessionStep.SERVICE_PICK, data=d, effects=effects)

            # persist in session data
            d["service_id"] = selected_service_id
            d["service_name"] = getattr(service, "name", None)
            d["duration"] = getattr(service, "duration_min", None)

            # next step: ask for slots (later you'll send slots list)
            effects.append({
                "kind": "SEND_TEXT",
                "to": "client",
                "text": f"מעולה ✅ {service.name}. עכשיו בחרי זמן פנוי.",
            })
            # or: effects.append({"kind": "SEND_SLOTS_LIST", ...})
            effects.append({"kind": "SEND_SLOTS_LIST", "to": "client", "rows": [   ]})
            return ReduceResult(flow=flow, step=SessionStep.SLOTS_PICK, data=d, effects=effects)

        if step == SessionStep.SLOTS_PICK:
            list_id = get_list_reply_id(msg)
            res: ListResponse = handle_list_response(list_id, data["chunked"])
            match res:
                case NavigationResponse():
                    data.update(
                        {
                            "chunk_index": res.chunk_index,
                            "client_step": step,
                            "error_message": None,
                        }
                    )
                    return ReduceResult(flow=flow, step=step, data=data, effects=effects)

                case SlotSelectionResponse():
                    slot: TimeSlot = res.slot
                    data.update(
                        {
                            "slot": slot.model_dump(),
                            "client_step": SessionStep.CONFIRM,
                            "error_message": None,
                        }
                    )
                    effects.append({"kind": "SEND_CONFIRM_BUTTONS", "to": "client", "rows":[]})
                    return ReduceResult(flow=flow, step=SessionStep.CONFIRM, data=data, effects=effects)

                case DisabledActionResponse():
                    data.update({"client_step": step, "error_message": res.message})
                    return ReduceResult(flow=flow, step=step, data=data, effects=effects)

                case UnknownActionResponse():
                    data.update({"client_step": step, "error_message": res.message})
                    return ReduceResult(flow=flow, step=step, data=data, effects=effects)

        if step == SessionStep.CONFIRM:
            # On confirm: finish client flow + trigger owner flow
            effects.append({"kind": "SEND_TEXT", "to": "client", "text": "Thanks. Sent to the owner for approval."})
            effects.append({"kind": "ENQUEUE_OWNER_APPROVAL", "payload": {"summary": d}})
            return ReduceResult(flow=flow, step=SessionStep.DONE, data=d, effects=effects)

    # Default fallback: reset safely
    effects.append({"kind": "SEND_TEXT", "to": "client", "text": "Let’s start over. What service do you need?"})
    return ReduceResult(flow=SessionFlow.CLIENT_BOOKING, step=SessionStep.SERVICE_PICK, data={}, effects=effects)
