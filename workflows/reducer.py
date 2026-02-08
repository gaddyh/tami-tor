from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from .models import (
    SessionState,
    SessionStep,
    InboundEvent,
    Service,
    Slot,
    parse_svc_row_id,
    parse_slot_row_id,
)

EffectKind = Literal[
    "SEND_TEXT",
    "SEND_SERVICES_LIST",
    "COMPUTE_SLOTS",
    "SEND_SLOTS_LIST",
    "SEND_CONFIRM_BUTTONS",
    "CREATE_BOOKING",
    "TRANSCRIBE_AUDIO",
]

@dataclass
class Effect:
    kind: EffectKind
    payload: Dict[str, Any]

@dataclass
class ReduceResult:
    state: SessionState
    effects: List[Effect]


CANCEL_WORDS = {"cancel", "ביטול", "בטל", "לבטל"}
YES_WORDS = {"yes", "ok", "confirm", "approve", "מאשר", "כן"}
NO_WORDS  = {"no", "cancel", "reject", "לא", "בטל"}

def _norm_text(t: Optional[str]) -> str:
    return (t or "").strip().lower()


def reduce_booking(
    *,
    state: SessionState,
    inbound: InboundEvent,
    business_id: str,
    client_id: str,
    services_cache: List[Service],
    slots_cache: List[Slot],
) -> ReduceResult:
    """
    Pure reducer:
    - reads state + inbound + caches
    - returns next state + effects
    - does NOT call activities
    """
    effects: List[Effect] = []

    # bookkeeping
    state.last_event_id = inbound.event_id
    state.last_inbound_kind = inbound.kind if inbound.kind in {"text","button","list","audio"} else "unknown"  # type: ignore[assignment]

    # audio is a special input: transcribe first, then re-run reducer with text
    if inbound.kind == "audio" and inbound.media:
        effects.append(Effect(
            kind="TRANSCRIBE_AUDIO",
            payload={"business_id": business_id, "client_id": client_id, "media": inbound.media, "event_id": inbound.event_id},
        ))
        return ReduceResult(state=state, effects=effects)

    # global cancel
    if inbound.kind == "text" and _norm_text(inbound.text) in CANCEL_WORDS:
        state.cancelled = True
        state.step = SessionStep.CANCELLED
        effects.append(Effect(
            kind="SEND_TEXT",
            payload={"client_id": client_id, "text": "בוטל. אם תרצה להתחיל מחדש — כתוב 'לקבוע תור'"},
        ))
        return ReduceResult(state=state, effects=effects)

    # INIT -> show services (entry)
    if state.step == SessionStep.INIT:
        state.step = SessionStep.SERVICE_PICK
        effects.append(Effect(
            kind="SEND_SERVICES_LIST",
            payload={"client_id": client_id, "services": services_cache},
        ))
        return ReduceResult(state=state, effects=effects)

    # SERVICE_PICK -> choose service -> compute slots -> send slots
    if state.step == SessionStep.SERVICE_PICK:
        sid = parse_svc_row_id(inbound.list_id)
        if not sid:
            if inbound.kind == "text" and inbound.text:
                effects.append(Effect("SEND_TEXT", {"client_id": client_id, "text": "בחר שירות מהרשימה 👇"}))
            return ReduceResult(state=state, effects=effects)

        state.data.service_id = sid
        svc = next((s for s in services_cache if s.id == sid), None)
        if svc:
            state.data.service_name = svc.name
            state.data.duration_min = svc.duration_min

        state.step = SessionStep.SLOTS_PICK
        state.data.chosen_slot_id = None
        state.data.confirmed = None

        effects.append(Effect("SEND_TEXT", {"client_id": client_id, "text": "מחשב זמינות..."}))
        effects.append(Effect("COMPUTE_SLOTS", {"business_id": business_id, "service_id": sid}))
        return ReduceResult(state=state, effects=effects)

    # SLOTS_PICK -> choose slot -> confirm buttons
    if state.step == SessionStep.SLOTS_PICK:
        chosen = parse_slot_row_id(inbound.list_id)
        if not chosen:
            if inbound.kind == "text" and inbound.text:
                effects.append(Effect("SEND_TEXT", {"client_id": client_id, "text": "בחר שעה מהרשימה 👇"}))
            return ReduceResult(state=state, effects=effects)

        state.data.chosen_slot_id = chosen
        state.step = SessionStep.CONFIRM
        state.data.confirmed = None

        effects.append(Effect(
            kind="SEND_CONFIRM_BUTTONS",
            payload={"client_id": client_id, "service_id": state.data.service_id, "slot_id": state.data.chosen_slot_id},
        ))
        return ReduceResult(state=state, effects=effects)

    # CONFIRM -> yes/no -> booking or cancel
    if state.step == SessionStep.CONFIRM:
        decided: Optional[bool] = None

        if inbound.kind == "button" and inbound.button_id:
            b = _norm_text(inbound.button_id)
            if b in YES_WORDS: decided = True
            elif b in NO_WORDS: decided = False

        if decided is None and inbound.kind == "text":
            t = _norm_text(inbound.text)
            if t in YES_WORDS: decided = True
            elif t in NO_WORDS: decided = False

        if decided is None:
            effects.append(Effect("SEND_TEXT", {"client_id": client_id, "text": "לא הבנתי. לאשר? ✅ / לבטל? ❌"}))
            return ReduceResult(state=state, effects=effects)

        state.data.confirmed = decided

        if decided is False:
            state.cancelled = True
            state.step = SessionStep.CANCELLED
            effects.append(Effect(
                "SEND_TEXT",
                {"client_id": client_id, "text": "בוטל. אם תרצה להתחיל מחדש — כתוב 'לקבוע תור'"},
            ))
            return ReduceResult(state=state, effects=effects)

        # decided True
        state.step = SessionStep.DONE  # optimistic
        effects.append(Effect(
            kind="CREATE_BOOKING",
            payload={
                "business_id": business_id,
                "client_id": client_id,
                "service_id": state.data.service_id,
                "slot_id": state.data.chosen_slot_id,
            },
        ))
        return ReduceResult(state=state, effects=effects)

    # DONE/CANCELLED ignore further input
    return ReduceResult(state=state, effects=effects)
