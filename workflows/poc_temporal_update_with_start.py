# poc_update_with_start_onefile.py
"""
Minimal Temporal PoC (single file):
- 1 workflow with durable state (count + last_text)
- 3 calls to Update-with-Start (same workflow id)
- worker + demo modes

Run:
  Terminal A: python poc_update_with_start_onefile.py worker
  Terminal B: python poc_update_with_start_onefile.py demo

Assumes Temporal dev server at localhost:7233
"""

from __future__ import annotations

import asyncio
import sys
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker
from workflows.main import update_client_workflow_with_start

from models.input import InboundEvent

# ---------- Demo ----------
async def run_demo() -> None:
    temporal = await Client.connect("localhost:7233")

    business_id = "demo-business"
    client_id = "demo-client24"
    wf_id = f"client:{business_id}:{client_id}"

    # 0) start (INIT -> SERVICE_PICK happens in ingest)
    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="e1", client_id=client_id, kind="text", text="hi"),
    )

    # 1) pick service
    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="e2", client_id=client_id, kind="list", list_id="svc:haircut"),
    )

    # 2) pick slot
    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="e3", client_id=client_id, kind="list", list_id="slot:10am"),
    )

    # 3) confirm
    await update_client_workflow_with_start(
        temporal_client=temporal,
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id="e4", client_id=client_id, kind="button", button_id="confirm"),
    )

    # Now it should actually complete
    handle = temporal.get_workflow_handle(wf_id)
    result = await handle.result()
    print("Workflow completed ✓", result)

    # Optional: query final state
    from workflows.client_session.workflow import ClientSessionWorkflow
    st = await handle.query(ClientSessionWorkflow.get_state)
    print("final state ->", st)




# ---------------------------
# Entrypoint
# ---------------------------

def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
