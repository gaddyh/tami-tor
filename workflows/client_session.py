# poc_update_with_start_onefile.py

from __future__ import annotations

import asyncio
import sys
from collections import deque
from typing import Deque

from temporalio import workflow
from temporalio.client import Client, WithStartWorkflowOperation
from temporalio.worker import Worker
from temporalio import common

from workflows.state import SessionState, InboundEvent, SessionStep

@workflow.defn
class ClientSessionWorkflow:
    def __init__(self) -> None:
        self.state = SessionState()
        self._inbox: Deque[InboundEvent] = deque()
        self._seen: set[str] = set()
        self._processed = 0  # just for demo exit condition

    # ---------- UPDATE ----------
    @workflow.update
    def ingest(self, ev: InboundEvent) -> dict:
        if not ev.event_id:
            raise ValueError("event_id required")

        if ev.event_id in self._seen:
            return {"accepted": True, "deduped": True}

        self._seen.add(ev.event_id)
        self._inbox.append(ev)

        return {"accepted": True, "deduped": False}

    # ---------- QUERY ----------
    @workflow.query
    def get_state(self) -> dict:
        return {
            "step": self.state.step,
            "service_id": self.state.data.service_id,
            "chosen_slot_id": self.state.data.chosen_slot_id,
            "cancelled": self.state.cancelled,
            "last_event_id": self.state.last_event_id,
        }

    # ---------- RUN LOOP ----------
    @workflow.run
    async def run(self) -> None:
        while True:
            await workflow.wait_condition(lambda: len(self._inbox) > 0)

            ev = self._inbox.popleft()
            self._processed += 1

            # Persist minimal state
            self.state.last_event_id = ev.event_id
            self.state.last_inbound_kind = ev.kind

            # --- Basic state machine demo ---
            if self.state.step == SessionStep.INIT:
                if ev.kind == "text":
                    self.state.step = SessionStep.SERVICE_PICK

            elif self.state.step == SessionStep.SERVICE_PICK:
                if ev.kind == "list" and ev.list_id:
                    self.state.data.service_id = ev.list_id
                    self.state.step = SessionStep.SLOTS_PICK

            elif self.state.step == SessionStep.SLOTS_PICK:
                if ev.kind == "list" and ev.list_id:
                    self.state.data.chosen_slot_id = ev.list_id
                    self.state.step = SessionStep.CONFIRM

            elif self.state.step == SessionStep.CONFIRM:
                if ev.kind == "button" and ev.button_id == "confirm":
                    self.state.data.confirmed = True
                    self.state.step = SessionStep.DONE

            # demo exit condition (remove in real system)
            if self._processed >= 3:
                return
