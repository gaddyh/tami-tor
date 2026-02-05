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
from observability.obs import instrument_io

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
    input_fn=lambda kind, eff, db, inbound, wi, session, state, adapter, business, provider_id, client_name, service_id, service_name, chosen_start, chosen_end: {
        "kind": kind,
        "eff": eff
    },
    output_fn=lambda result: result,
    redact=True
)
async def dispatch_effect(kind=kind,
                eff=eff,
                db=db,
                inbound=inbound,
                wi=wi,
                session=session,
                state=state,
                adapter=adapter,
                business=business,
                provider_id=provider_id,
                client_name=client_name,
                service_id=service_id,
                service_name=service_name,
                chosen_start=chosen_start,
                chosen_end=chosen_end,) -> None:
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

    await handler(eff=eff, db=db, inbound=inbound, wi=wi, session=session, state=state, adapter=adapter, business=business, provider_id=provider_id, client_name=client_name, service_id=service_id, service_name=service_name, chosen_start=chosen_start, chosen_end=chosen_end)
