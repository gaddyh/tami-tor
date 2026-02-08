from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

from .models import BookingParams, InboundEvent, Service, Slot, SessionState, SessionStep
from .reducer import reduce_booking, Effect


DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=20),
    maximum_attempts=5,
)

with workflow.unsafe.imports_passed_through():
    from workflows.activities import (
        load_services,
        compute_slots,
        send_text,
        send_services_list,
        send_slots_list,
        send_confirm_buttons,
        create_booking,
        transcribe_audio,
    )


@workflow.defn(name="BookingWorkflow")
class BookingWorkflow:
    @workflow.init
    def __init__(self, p: BookingParams) -> None:
        self.p = p  # business_id + client_id live here, always available

        self.state = {
            "step": "init",
            "cancelled": False,
            "service_id": None,
            "slot_id": None,
            "confirmed": None,
        }

        self.services = []
        self.slots = []
        self.booking_id = None

  

    @workflow.query
    def get_state(self) -> dict:
        return {
            "version": self.state.version,
            "actor": self.state.actor.value,
            "step": self.state.step.value,
            "cancelled": self.state.cancelled,
            "error_message": self.state.error_message,
            "last_event_id": self.state.last_event_id,
            "last_inbound_kind": self.state.last_inbound_kind,
            "data": {
                "client_name": self.state.data.client_name,
                "service_id": self.state.data.service_id,
                "service_name": self.state.data.service_name,
                "duration_min": self.state.data.duration_min,
                "availability_cursor": self.state.data.availability_cursor,
                "chosen_slot_id": self.state.data.chosen_slot_id,
                "confirmed": self.state.data.confirmed,
            },
            "services_loaded": len(self.services),
            "slots_loaded": len(self.slots),
            "last_booking_id": self._last_booking_id,
        }

    async def _exec_effect(self, eff: Effect) -> None:
        if self._business_id is None or self._client_id is None:
            raise RuntimeError("Workflow not initialized (missing business_id/client_id)")

        if eff.kind == "SEND_TEXT":
            await workflow.execute_activity(
                send_text,
                eff.payload,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=DEFAULT_RETRY,
            )
            return

        if eff.kind == "SEND_SERVICES_LIST":
            await workflow.execute_activity(
                send_services_list,
                eff.payload,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=DEFAULT_RETRY,
            )
            return

        if eff.kind == "COMPUTE_SLOTS":
            self.slots = await workflow.execute_activity(
                compute_slots,
                eff.payload,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=DEFAULT_RETRY,
            )
            # send the slots list immediately (driver responsibility)
            await workflow.execute_activity(
                send_slots_list,
                {"client_id": self._client_id, "slots": self.slots},
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=DEFAULT_RETRY,
            )
            return

        if eff.kind == "SEND_SLOTS_LIST":
            await workflow.execute_activity(
                send_slots_list,
                eff.payload,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=DEFAULT_RETRY,
            )
            return

        if eff.kind == "SEND_CONFIRM_BUTTONS":
            await workflow.execute_activity(
                send_confirm_buttons,
                eff.payload,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=DEFAULT_RETRY,
            )
            return

        if eff.kind == "CREATE_BOOKING":
            booking_id = await workflow.execute_activity(
                create_booking,
                eff.payload,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=DEFAULT_RETRY,
            )
            self._last_booking_id = booking_id
            await workflow.execute_activity(
                send_text,
                {"client_id": self._client_id, "text": f"אושר ✅ הזמנה נוצרה: {booking_id}"},
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=DEFAULT_RETRY,
            )
            return

        if eff.kind == "TRANSCRIBE_AUDIO":
            # transcribe and re-run reducer as text (no signal needed)
            text = await workflow.execute_activity(
                transcribe_audio,
                {"business_id": self._business_id, "client_id": self._client_id, "media": eff.payload["media"]},
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=DEFAULT_RETRY,
            )
            # synthetic inbound
            synthetic = InboundEvent(
                event_id=eff.payload.get("event_id", "transcribed"),
                client_id=self._client_id,
                kind="text",
                text=(text or "").strip(),
            )
            await self._apply_inbound(synthetic)
            return

        raise ValueError(f"Unknown effect kind: {eff.kind}")

    async def _apply_inbound(self, ev: InboundEvent) -> Dict[str, Any]:
        rr = reduce_booking(
            state=self.state,
            inbound=ev,
            business_id=self._business_id or "",
            client_id=self._client_id or ev.client_id,
            services_cache=self.services,
            slots_cache=self.slots,
        )
        self.state = rr.state
        for eff in rr.effects:
            await self._exec_effect(eff)

        return {
            "ok": True,
            "step": self.state.step.value,
            "cancelled": self.state.cancelled,
            "data": {
                "service_id": self.state.data.service_id,
                "chosen_slot_id": self.state.data.chosen_slot_id,
                "confirmed": self.state.data.confirmed,
            },
            "booking_id": self._last_booking_id,
        }

    # ---- UPDATE: inbound command ----
    @workflow.update(name="inbound")
    async def inbound(self, ev: InboundEvent) -> Dict[str, Any]:
        # reject if finished
        if self.state.step in {SessionStep.DONE, SessionStep.CANCELLED}:
            return {
                "ok": False,
                "error": "workflow_finished",
                "step": self.state.step.value,
                "booking_id": self._last_booking_id,
            }

        return await self._apply_inbound(ev)

    @workflow.run
    async def run(self, p: BookingParams) -> Dict[str, Any]:
        self._business_id = p.business_id
        self._client_id = p.client_id

        # preload services once
        self.services = await workflow.execute_activity(
            load_services,
            {"business_id": p.business_id},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        # idle until done/cancelled
        await workflow.wait_condition(lambda: self.state.step in {SessionStep.DONE, SessionStep.CANCELLED})

        if self.state.step == SessionStep.DONE:
            return {"ok": True, "status": "done", "booking_id": self._last_booking_id}
        return {"ok": False, "status": "cancelled"}
