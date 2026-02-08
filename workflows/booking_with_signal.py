from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Optional, List, Literal, Dict, Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from workflows.state import InboundEvent, SessionState, BookingParams, Service, Slot, SessionStep, parse_svc_row_id, parse_slot_row_id
# ----------------------------
# Retry policy
# ----------------------------

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


# ----------------------------
# Workflow
# ----------------------------

@workflow.defn(name="BookingWorkflow")
class BookingWorkflow:
    def __init__(self) -> None:
        # Single authoritative state
        self.state: SessionState = SessionState()

        # Ephemeral UI caches (ok to keep in workflow memory)
        self.services: List[Service] = []
        self.slots: List[Slot] = []

        # Keep params around for signals (esp. audio transcription)
        self._business_id: Optional[str] = None
        self._client_id: Optional[str] = None

    # ---- ONE signal ----
    @workflow.signal
    async def on_inbound(self, ev: InboundEvent) -> None:
        self.state.last_event_id = ev.event_id
        if ev.kind in {"text", "button", "list", "audio"}:
            self.state.last_inbound_kind = ev.kind  # type: ignore[assignment]
        else:
            self.state.last_inbound_kind = "unknown"

        # Audio -> transcribe -> re-inject as text
        if ev.kind == "audio" and ev.media:
            # If workflow hasn't started (rare), we still try with stored ids if available.
            business_id = self._business_id
            client_id = self._client_id or ev.client_id

            try:
                text = await workflow.execute_activity(
                    transcribe_audio,
                    {"business_id": business_id, "client_id": client_id, "media": ev.media},
                    start_to_close_timeout=timedelta(seconds=120),
                    retry_policy=DEFAULT_RETRY,
                )
            except Exception:
                return

            ev = InboundEvent(
                event_id=ev.event_id,
                client_id=ev.client_id,
                kind="text",
                text=(text or "").strip(),
            )

        self._apply_event(ev)

    def _apply_event(self, ev: InboundEvent) -> None:
        # Global cancel keywords
        if ev.kind == "text" and ev.text:
            t = ev.text.strip().lower()
            if t in {"cancel", "ביטול", "בטל", "לבטל"}:
                self.state.cancelled = True
                self.state.step = SessionStep.CANCELLED
                return

        # Step-specific handling
        step = self.state.step

        if step == SessionStep.SERVICE_PICK:
            sid = parse_svc_row_id(ev.list_id)
            if sid:
                self.state.data.service_id = sid

                # Optional enrichment from cached services
                svc = next((s for s in self.services if s.id == sid), None)
                if svc:
                    self.state.data.service_name = svc.name
                    self.state.data.duration_min = svc.duration_min
                return

        if step == SessionStep.SLOTS_PICK:
            sl = parse_slot_row_id(ev.list_id)
            if sl:
                self.state.data.chosen_slot_id = sl
                return

        if step == SessionStep.CONFIRM:
            if ev.button_id:
                b = ev.button_id.strip().lower()
                if b in {"confirm", "yes", "ok", "approve", "מאשר"}:
                    # encode confirm as chosen_slot_id present + no cancellation; you can add explicit flag if you want
                    # Better: add state.data.confirmed: Optional[bool]
                    # For now: store in error_message slot is dumb; so we add a dedicated field below.
                    self._set_confirmed(True)
                    return
                if b in {"cancel", "no", "reject", "לא", "בטל"}:
                    self._set_confirmed(False)
                    return

            if ev.kind == "text" and ev.text:
                t = ev.text.strip().lower()
                if t in {"yes", "ok", "confirm", "מאשר", "כן"}:
                    self._set_confirmed(True)
                    return
                if t in {"no", "cancel", "לא", "בטל"}:
                    self._set_confirmed(False)
                    return

    # --- tiny helper to avoid scattering another field all over ---
    def _set_confirmed(self, val: bool) -> None:
        # If you want it in SessionData properly, add:
        # confirmed: Optional[bool] = None
        # For now we store it on state.error_message is wrong; so do it properly:
        # (Yes, I'm mutating the dataclass shape at runtime? No.)
        # => We actually add it in state as an attribute here (bad idea).
        # So: just keep it as a workflow field instead? Also bad.
        #
        # Best: extend SessionData. Do it.
        if not hasattr(self.state.data, "confirmed"):  # type: ignore[attr-defined]
            # This is only here to avoid breaking your pasted model immediately.
            # Remove this hack after you add confirmed to SessionData.
            setattr(self.state.data, "confirmed", None)  # type: ignore[attr-defined]

        setattr(self.state.data, "confirmed", val)  # type: ignore[attr-defined]

    def _get_confirmed(self) -> Optional[bool]:
        return getattr(self.state.data, "confirmed", None)  # type: ignore[attr-defined]

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
            },
            "services_loaded": len(self.services),
            "slots_loaded": len(self.slots),
        }

    @workflow.run
    async def run(self, p: BookingParams) -> dict:
        self._business_id = p.business_id
        self._client_id = p.client_id

        # 0) load services
        self.services = await workflow.execute_activity(
            load_services,
            {"business_id": p.business_id},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        # 1) show services
        self.state.step = SessionStep.SERVICE_PICK
        await workflow.execute_activity(
            send_services_list,
            {"client_id": p.client_id, "services": self.services},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        await workflow.wait_condition(
            lambda: self.state.cancelled or self.state.data.service_id is not None
        )
        if self.state.cancelled:
            return await self._finish_cancel(p)

        # 2) compute + show slots
        await workflow.execute_activity(
            send_text,
            {"client_id": p.client_id, "text": "מחשב זמינות..."},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        self.slots = await workflow.execute_activity(
            compute_slots,
            {"business_id": p.business_id, "service_id": self.state.data.service_id},
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )

        self.state.step = SessionStep.SLOTS_PICK
        await workflow.execute_activity(
            send_slots_list,
            {"client_id": p.client_id, "slots": self.slots},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        await workflow.wait_condition(
            lambda: self.state.cancelled or self.state.data.chosen_slot_id is not None
        )
        if self.state.cancelled:
            return await self._finish_cancel(p)

        # 3) confirm
        self.state.step = SessionStep.CONFIRM
        await workflow.execute_activity(
            send_confirm_buttons,
            {
                "client_id": p.client_id,
                "service_id": self.state.data.service_id,
                "slot_id": self.state.data.chosen_slot_id,
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        await workflow.wait_condition(
            lambda: self.state.cancelled or self._get_confirmed() is not None
        )
        if self.state.cancelled or self._get_confirmed() is False:
            return await self._finish_cancel(p)

        # 4) create booking
        booking_id = await workflow.execute_activity(
            create_booking,
            {
                "business_id": p.business_id,
                "client_id": p.client_id,
                "service_id": self.state.data.service_id,
                "slot_id": self.state.data.chosen_slot_id,
            },
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )

        self.state.step = SessionStep.DONE
        await workflow.execute_activity(
            send_text,
            {"client_id": p.client_id, "text": f"אושר ✅ הזמנה נוצרה: {booking_id}"},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        return {"ok": True, "status": "done", "booking_id": booking_id}

    async def _finish_cancel(self, p: BookingParams) -> dict:
        self.state.step = SessionStep.CANCELLED
        await workflow.execute_activity(
            send_text,
            {"client_id": p.client_id, "text": "בוטל. אם תרצה להתחיל מחדש — כתוב 'לקבוע תור'"},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )
        return {"ok": False, "status": "cancelled"}
