# workflows/client_session/workflow.py
from __future__ import annotations
from datetime import timedelta
from typing import Optional, Dict, Any, Tuple

from temporalio import workflow
from temporalio.common import RetryPolicy

from models.session_state import SessionState, SessionStep
from models.input import InboundEvent
from models.service import Service
from models.llm_bootstrap import BookingBootstrap

from workflows.client_session.inbox import TextInbox
from workflows.client_session.router import route_intent, extract_bootstrap, step_delta
from workflows.client_session.flow_create import run_create
from workflows.client_session.flow_read import run_read
from workflows.client_session.flow_delete import run_delete
from workflows.client_session.flow_update import run_update
from workflows.helper import handle_list_response, ListResponse, ActionType

DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)

@workflow.defn
class ClientSessionWorkflow:
    SessionStep = SessionStep  # for submodules

    def __init__(self) -> None:
        self.state = SessionState()
        self._business_id: Optional[str] = None
        self._client_id: Optional[str] = None
        self.inbox = TextInbox()

        self.bootstrap: Optional[BookingBootstrap] = None

    @property
    def business_id(self) -> str:
        assert self._business_id
        return self._business_id

    @property
    def client_id(self) -> str:
        assert self._client_id
        return self._client_id

    def apply_common_delta(self, delta: Dict[str, Any]) -> None:
        self.state.data.update(delta)

    @workflow.update
    async def ingest(self, ev: InboundEvent) -> Dict[str, Any]:
        if not ev.event_id:
            raise ValueError("event_id required")

        if ev.kind == "text" and ev.text:
            self.inbox.ingest_text(ev.text)
            self.state.data.last_text_input = ev.text.strip()
            if ev.text.strip().lower() in {"cancel", "stop", "בטל"}:
                self.state.cancelled = True
                self.state.step = SessionStep.CANCELLED
                return {"accepted": True, "action": "cancelled"}

        if ev.list_id:
            if ev.list_id.startswith("svc:"):
                self.state.data.service_id = ev.list_id.replace("svc:", "", 1)
            elif ev.list_id.startswith("slot:") or ev.list_id.startswith("nav"):
                id = ev.list_id.replace("slot:", "", 1)
                response: ListResponse = handle_list_response(id, self.state.data.chunked)
                if response.action == ActionType.SLOT_SELECTED:
                    self.state.data.chosen_slot_id = id
                    self.state.data.chosen_slot = response.slot
                if response.action == ActionType.NAVIGATE:
                    self.state.data.chunked_index = response.chunk_index
                    await workflow.execute_activity(
                        "send_slots_list",
                        {"client_id": self.client_id, "chunked": self.state.data.chunked, "index": self.state.data.chunked_index},
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=DEFAULT_RETRY,
                    )
            elif ev.list_id.startswith("booking:"):
                self.state.data.booking_id = ev.list_id.replace("booking:", "", 1)

        if ev.kind == "button" and ev.button_id in ("confirm", "cancel"):
            self.state.data.confirmed = (ev.button_id == "confirm")

        return {"accepted": True}

    @workflow.query
    def get_state(self) -> dict:
        return {"step": self.state.step, "data": self.state.data.model_dump()}

    @workflow.run
    async def run(self) -> dict:
        wf_id = workflow.info().workflow_id
        self._business_id, self._client_id = self._parse_wf_id(wf_id)

        services: list[Service] = await workflow.execute_activity(
            "load_services",
            {"business_id": self.business_id},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )

        self.state.step = SessionStep.ROUTE
        await workflow.wait_condition(lambda: self.state.cancelled or self.inbox.initial is not None)
        if self.state.cancelled:
            return await self.finish_cancel("route")

        r = await route_intent(self.inbox.initial or "", self.business_id, self.client_id)
        if r.intent == "OTHER":
            await workflow.execute_activity(
                "send_text",
                {"client_id": self.client_id, "text": "לא הבנתי. כתוב: לקבוע / לשנות / לבטל / להציג תורים."},
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=DEFAULT_RETRY,
            )
            self.state.step = SessionStep.DONE
            return {"ok": False, "status": "other"}

        self.bootstrap = await extract_bootstrap(
            r.intent,
            self.inbox.initial or "",
            services,
            self.business_id,
            self.client_id,
        )

        # dispatch with typed payload (each flow can accept BaseModel or dict; pick one)
        if self.bootstrap.intent == "CREATE":
            return await run_create(self, services, self.bootstrap.payload.model_dump() if self.bootstrap.payload else {})
        if self.bootstrap.intent == "READ":
            return await run_read(self, self.bootstrap.payload.model_dump() if self.bootstrap.payload else {})
        if self.bootstrap.intent == "DELETE":
            return await run_delete(self, self.bootstrap.payload.model_dump() if self.bootstrap.payload else {})
        return await run_update(self, services, self.bootstrap.payload.model_dump() if self.bootstrap.payload else {})

    async def wait_with_fallback(self, *, intent: str, step: str, predicate, context: dict, apply_delta) -> None:
        while True:
            await workflow.wait_condition(lambda: predicate() or self.state.cancelled or self.inbox.has_next())
            if self.state.cancelled or predicate():
                return
            txt = self.inbox.pop_next()
            if not txt:
                continue
            d = await step_delta(intent, step, txt, context)
            apply_delta(d)

    async def finish_cancel(self, at: str) -> dict:
        await workflow.execute_activity(
            "send_text",
            {"client_id": self.client_id, "text": "הבקשה בוטלה ❌"},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=DEFAULT_RETRY,
        )
        return {"ok": False, "status": "cancelled", "at": at}

    def _parse_wf_id(self, wf_id: str) -> Tuple[str, str]:
        parts = wf_id.split(":", 2)
        if len(parts) != 3 or parts[0] != "client":
            raise ValueError(f"bad workflow id: {wf_id}")
        return parts[1], parts[2]
