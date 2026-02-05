# effects/registry.py
from __future__ import annotations

from typing import Awaitable, Callable, Dict, Any

from handlers.effects.create_reminder import handle_create_reminder
from handlers.effects.send_service_list import handle_send_service_list
from handlers.effects.fetch_events import handle_fetch_events
from handlers.effects.send_slots_list import handle_send_slots_list
from handlers.effects.send_confirm_buttons import handle_send_confirm_buttons
from handlers.effects.create_event import handle_create_event
from handlers.effects.send_confirmation import handle_send_confirmation


Handler = Callable[..., Awaitable[None]]

EFFECT_REGISTRY: Dict[str, Handler] = {
    "CREATE_REMINDER": handle_create_reminder,
    "SEND_SERVICE_LIST": handle_send_service_list,
    "FETCH_EVENTS": handle_fetch_events,
    "SEND_SLOTS_LIST": handle_send_slots_list,
    "SEND_CONFIRM_BUTTONS": handle_send_confirm_buttons,
    "CREATE_EVENT": handle_create_event,
    "SEND_CONFIRMATION": handle_send_confirmation,
}

@instrument_io(
    name="dispatch_effect",
    meta={"operation": "dispatch_effect"},
    input_fn=lambda kind, eff, ctx: {
        "kind": kind,
        "eff": eff,
        "ctx": ctx,
    },
    output_fn=lambda result: result,
    redact=True
)
async def dispatch_effect(*, kind: str, eff: dict, **ctx: Any) -> None:
    """
    Dispatches an effect by kind.

    Pass any shared context via **ctx (db, adapter, wi, session, state, business, etc.).
    Unknown kinds are ignored by default (or raise, your choice).
    """
    handler = EFFECT_REGISTRY.get(kind)
    if not handler:
        # choose one:
        # return
        raise KeyError(f"Unhandled effect kind: {kind}")

    await handler(eff=eff, **ctx)
