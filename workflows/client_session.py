# workflows/client_session.py

from __future__ import annotations

from datetime import timedelta
from typing import Optional, Dict, Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from models.session_state import SessionState, SessionStep
from models.input import InboundEvent
from agents.core import get_llm_bootstrap

DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)

@workflow.defn
class ClientSessionWorkflow:
    def __init__(self) -> None:
        self.state = SessionState()
        self._business_id: Optional[str] = None
        self._client_id: Optional[str] = None

    # ---------------- UPDATE ----------------
    @workflow.update
    def ingest(self, ev: InboundEvent) -> Dict[str, Any]:
        if not ev.event_id:
            raise ValueError("event_id required")

        text = ev.text.lower() if ev.text else ""
        self.state.data.last_text_input = text

        # Global cancel
        if ev.kind == "text" and text in {"cancel", "stop", "בטל"}:
            self.state.cancelled = True
            self.state.step = SessionStep.CANCELLED
            return {"accepted": True, "action": "cancelled"}

        # ✅ Content-based mapping (robust to early/out-of-order inputs)
        if ev.list_id:
            if ev.list_id.startswith("svc:"):
                self.state.data.service_id = ev.list_id
                return {"accepted": True, "mapped": "service_id"}
            if ev.list_id.startswith("slot:"):
                self.state.data.chosen_slot_id = ev.list_id
                return {"accepted": True, "mapped": "chosen_slot_id"}

        if ev.kind == "button" and ev.button_id in ("confirm", "cancel"):
            self.state.data.confirmed = (ev.button_id == "confirm")
            return {"accepted": True, "mapped": "confirmed"}

        return {"accepted": True, "mapped": None}


    # ---------------- QUERY ----------------
    @workflow.query
    def get_state(self) -> dict:
        return {
            "step": self.state.step,
            "cancelled": self.state.cancelled,
            "service_id": self.state.data.service_id,
            "chosen_slot_id": self.state.data.chosen_slot_id,
            "confirmed": self.state.data.confirmed,
        }

    # ---------------- RUN ----------------
    @workflow.run
    async def run(self) -> dict:
        wf_id = workflow.info().workflow_id
        self._business_id, self._client_id = self._parse_wf_id(wf_id)

        self.state.step = SessionStep.SERVICE_PICK

        # 0) load services
        services = await workflow.execute_activity(
            "load_services",
            {"business_id": self._business_id},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        # text message
        if self.state.data.last_text_input:
            # TODO: handle service selection from previous input
            result = get_llm_bootstrap(self.state.data.last_text_input, services)
            print(result)
            pass

        # 1) show services
        await workflow.execute_activity(
            "send_services_list",
            {
                "client_id": self._client_id,
                "services": services,
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        await workflow.wait_condition(
            lambda: self.state.cancelled or self.state.data.service_id is not None
        )

        if self.state.cancelled:
            return await self._finish_cancel("service_pick")

        # 2) compute + show slots
        await workflow.execute_activity(
            "send_text",
            {
                "client_id": self._client_id,
                "text": "מחשב זמינות...",
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        self.state.step = SessionStep.SLOTS_PICK

        slots = await workflow.execute_activity(
            "compute_slots",
            {
                "business_id": self._business_id,
                "service_id": self.state.data.service_id,
            },
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )


        await workflow.execute_activity(
            "send_slots_list",
            {
                "client_id": self._client_id,
                "slots": slots,
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        await workflow.wait_condition(
            lambda: self.state.cancelled or self.state.data.chosen_slot_id is not None
        )

        if self.state.cancelled:
            return await self._finish_cancel("slots_pick")

        # 3) confirm
        self.state.step = SessionStep.CONFIRM

        await workflow.execute_activity(
            "send_confirm_buttons",
            {
                "client_id": self._client_id,
                "service_id": self.state.data.service_id,
                "slot_id": self.state.data.chosen_slot_id,
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        await workflow.wait_condition(
            lambda: self.state.cancelled or self.state.data.confirmed is not None
        )

        if self.state.cancelled or self.state.data.confirmed is False:
            self.state.step = SessionStep.CANCELLED
            return await self._finish_cancel("confirm")

        # 4) create booking
        booking_id = await workflow.execute_activity(
            "create_booking",
            {
                "business_id": self._business_id,
                "client_id": self._client_id,
                "service_id": self.state.data.service_id,
                "slot_id": self.state.data.chosen_slot_id,
            },
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )

        self.state.step = SessionStep.DONE

        await workflow.execute_activity(
            "send_text",
            {
                "client_id": self._client_id,
                "text": f"אושר ✅ הזמנה נוצרה: {booking_id}",
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        return {
            "ok": True,
            "status": "done",
            "booking_id": booking_id,
        }

    # ---------------- Helpers ----------------

    def _parse_wf_id(self, wf_id: str) -> tuple[str, str]:
        # expected: client:{business_id}:{client_id}
        parts = wf_id.split(":", 2)
        if len(parts) != 3 or parts[0] != "client":
            raise ValueError(f"bad workflow id: {wf_id}")
        return parts[1], parts[2]

    async def _finish_cancel(self, at: str) -> dict:
        await workflow.execute_activity(
            "send_text",
            {
                "client_id": self._client_id,
                "text": "הבקשה בוטלה ❌",
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )
        return {"ok": False, "status": "cancelled", "at": at}
