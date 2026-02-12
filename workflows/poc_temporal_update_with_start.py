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

TASK_QUEUE = "poc-task-queue"
WF_ID = "client:demo:123"


# ---------------------------
# Models
# ---------------------------

from workflows.state import SessionState, InboundEvent

# ---------------------------
# Workflow
# ---------------------------

@workflow.defn
class ClientSessionWorkflow:
    def __init__(self) -> None:
        self.state = SessionState()
        self._inbox: Deque[InboundEvent] = deque()
        self._seen: set[str] = set()

    @workflow.update
    def ingest(self, ev: InboundEvent) -> dict:
        # Keep update handler fast: validate + dedupe + enqueue + ACK
        if not ev.message_id:
            raise ValueError("message_id required")
        if ev.message_id in self._seen:
            return {"accepted": True, "deduped": True}

        self._seen.add(ev.message_id)
        self._inbox.append(ev)
        return {"accepted": True, "deduped": False}

    @workflow.query
    def get_state(self) -> dict:
        return {"count": self.state.count, "last_text": self.state.last_text}

    @workflow.run
    async def run(self) -> None:
        # Process exactly 3 messages then complete (so the demo ends)
        while self.state.count < 3:
            await workflow.wait_condition(lambda: len(self._inbox) > 0)
            ev = self._inbox.popleft()
            self.state.count += 1
            self.state.last_text = ev.text


# ---------------------------
# Worker
# ---------------------------

from temporalio.client import Client

from workflows.main import TASK_QUEUE


# ---------------------------
# Client demo (3 update-with-start calls)
# ---------------------------
async def run_demo():
    client = await Client.connect("localhost:7233")
    business_id = "demo-business"
    client_id = "demo-client1"
    await update_client_workflow_with_start(temporal_client=client, business_id=business_id, client_id=client_id, ev=InboundEvent("e1", "client1", "text", text="hi"))
    await update_client_workflow_with_start(temporal_client=client, business_id=business_id, client_id=client_id, ev=InboundEvent("e2", "client1", "list", list_id="svc:haircut"))
    await update_client_workflow_with_start(temporal_client=client, business_id=business_id, client_id=client_id, ev=InboundEvent("e3", "client1", "list", list_id="slot:10am"))

    handle = client.get_workflow_handle(WF_ID)
    await handle.result()
    print("Workflow completed ✓")


# ---------------------------
# Entrypoint
# ---------------------------

def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
