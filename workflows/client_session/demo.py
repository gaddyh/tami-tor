# workflows/client_session/demo.py
from __future__ import annotations

import asyncio
import sys
from temporalio.client import Client

from workflows.main import update_client_workflow_with_start
from models.input import InboundEvent


async def _run_create(temporal: Client, business_id: str, client_id: str) -> None:
    wf_id = f"client:{business_id}:{client_id}"

    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="c1", client_id=client_id, kind="text", text="hi"),
    )
    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="c2", client_id=client_id, kind="list", list_id="svc:haircut"),
    )
    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="c3", client_id=client_id, kind="list", list_id="slot:10am"),
    )
    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="c4", client_id=client_id, kind="button", button_id="confirm"),
    )

    handle = temporal.get_workflow_handle(wf_id)
    result = await handle.result()
    print("CREATE ✓", result)


async def _run_read(temporal: Client, business_id: str, client_id: str) -> None:
    wf_id = f"client:{business_id}:{client_id}"

    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="r1", client_id=client_id, kind="text", text="show my bookings"),
    )

    handle = temporal.get_workflow_handle(wf_id)
    result = await handle.result()
    print("READ ✓", result)


async def _run_delete(temporal: Client, business_id: str, client_id: str) -> None:
    wf_id = f"client:{business_id}:{client_id}"

    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="d1", client_id=client_id, kind="text", text="cancel my booking"),
    )

    # Pick booking from the list UI (ingest maps booking:<id> -> state.data.booking_id)
    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="d2", client_id=client_id, kind="list", list_id="booking:bk_demo_001"),
    )

    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="d3", client_id=client_id, kind="button", button_id="confirm"),
    )

    handle = temporal.get_workflow_handle(wf_id)
    result = await handle.result()
    print("DELETE ✓", result)


async def _run_update(temporal: Client, business_id: str, client_id: str) -> None:
    wf_id = f"client:{business_id}:{client_id}"

    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="u1", client_id=client_id, kind="text", text="update my booking"),
    )

    # Pick booking to update
    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="u2", client_id=client_id, kind="list", list_id="booking:bk_demo_001"),
    )

    # Choose new slot (and optionally service)
    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="u3", client_id=client_id, kind="list", list_id="slot:11am"),
    )

    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="u4", client_id=client_id, kind="button", button_id="confirm"),
    )

    handle = temporal.get_workflow_handle(wf_id)
    result = await handle.result()
    print("UPDATE ✓", result)


async def main_async(mode: str) -> None:
    temporal = await Client.connect("localhost:7233")

    business_id = "demo-salon"
    # Use a different client_id per mode to avoid collisions during dev
    client_id = {
        "create": "demo-client11-create7",
        "read": "demo-client-read6",
        "delete": "demo-client-delete6",
        "update": "demo-client-update6",
    }.get(mode, "demo-client-create6")

    if mode == "create":
        await _run_create(temporal, business_id, client_id)
    elif mode == "read":
        await _run_read(temporal, business_id, client_id)
    elif mode == "delete":
        await _run_delete(temporal, business_id, client_id)
    elif mode == "update":
        await _run_update(temporal, business_id, client_id)
    else:
        raise SystemExit("usage: python -m workflows.client_session.demo [create|read|delete|update]")


def main() -> None:
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "create"
    asyncio.run(main_async(mode))


if __name__ == "__main__":
    main()
