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
from temporalio.client import Client, WithStartWorkflowOperation
from temporalio.worker import Worker
from temporalio import common

from models.session_state import SessionState
from models.input import InboundEvent

TASK_QUEUE = "poc-task-queue"
WF_ID = "client:demo:123"


# ---------------------------
# Workflow
# ---------------------------

@workflow.defn
class ProviderWorkflow:
    def __init__(self) -> None:
        self.state = SessionState()
        self._inbox: Deque[InboundEvent] = deque()
        self._seen: set[str] = set()

    @workflow.update
    def ingest(self, ev: InboundEvent) -> dict:
        # Keep update handler fast: validate + dedupe + enqueue + ACK
        if not ev.event_id:
            raise ValueError("event_id required")
        if ev.event_id in self._seen:
            return {"accepted": True, "deduped": True}

        self._seen.add(ev.event_id)
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

async def run_worker() -> None:
    client = await Client.connect("localhost:7233")
    worker = Worker(client, task_queue=TASK_QUEUE, workflows=[ProviderWorkflow])
    print(f"Worker running. task_queue={TASK_QUEUE}")
    await worker.run()


# ---------------------------
# Client demo (3 update-with-start calls)
# ---------------------------

async def send_update_with_start(client: Client, ev: InboundEvent) -> None:
    # WithStartWorkflowOperation is REQUIRED and is single-use. Create one per call.
    # task_queue goes HERE (not as a kwarg to execute_update_with_start_workflow).
    start_op = WithStartWorkflowOperation(
        ProviderWorkflow.run,
        id=WF_ID,
        task_queue=TASK_QUEUE,
        id_conflict_policy=common.WorkflowIDConflictPolicy.USE_EXISTING,
    )

    res = await client.execute_update_with_start_workflow(
        ProviderWorkflow.ingest,
        ev,
        start_workflow_operation=start_op,
    )
    print("update result ->", res)

    handle = await start_op.workflow_handle()
    st = await handle.query(ProviderWorkflow.get_state)
    print("state ->", st)


async def run_demo() -> None:
    client = await Client.connect("localhost:7233")

    await send_update_with_start(client, InboundEvent("m1", "hello"))
    await send_update_with_start(client, InboundEvent("m2", "world"))
    await send_update_with_start(client, InboundEvent("m3", "done"))

    # Wait for completion (should be quick after 3rd message)
    handle = client.get_workflow_handle(WF_ID)
    await handle.result()
    print("completed ✓")


# ---------------------------
# Entrypoint
# ---------------------------

def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("worker", "demo"):
        print("Usage: python poc_update_with_start_onefile.py [worker|demo]")
        raise SystemExit(2)

    if sys.argv[1] == "worker":
        asyncio.run(run_worker())
    else:
        asyncio.run(run_demo())


if __name__ == "__main__":
    main()
