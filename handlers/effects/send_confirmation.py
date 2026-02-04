# effects/handlers/send_confirmation.py
from __future__ import annotations
from models.work_item import WorkItem
from adapters.cloud_api import CloudAPIAdapter

def _should_run(eff: dict) -> bool:
    return eff.get("to") == "client"

async def handle_send_confirmation(*, eff: dict, wi:WorkItem, adapter:CloudAPIAdapter, **_) -> None:
    if not _should_run(eff):
        return

    await adapter.send_message(
        recipient=wi.client_id,
        message=eff.get("text", ""),
    )
