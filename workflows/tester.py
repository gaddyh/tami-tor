# tester.py
import asyncio
import uuid
from temporalio.client import Client

from workflows.main import signal_booking_workflow
from workflows.booking_with_signal import BookingWorkflow
from workflows.state import InboundEvent

TASK_QUEUE = "booking"


def _eid() -> str:
    return f"e:{uuid.uuid4().hex[:10]}"


async def _wait_step(client: Client, wf_id: str, want: str, timeout_s: float = 10.0) -> dict:
    handle = client.get_workflow_handle(wf_id)
    deadline = asyncio.get_event_loop().time() + timeout_s
    last = None
    while asyncio.get_event_loop().time() < deadline:
        st = await handle.query(BookingWorkflow.get_state)
        last = st
        if st.get("step") == want:
            return st
        await asyncio.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for step={want}. Last={last}")


async def run_happy_path() -> None:
    business_id = "biz_1234"
    client_id = "client_25"
    wf_id = f"booking:{business_id}:{client_id}"

    temporal_client = await Client.connect("localhost:7233")

    # 1) start
    await signal_booking_workflow(
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id=_eid(), client_id=client_id, kind="text", text="לקבוע תור"),
        temporal_client=temporal_client,
    )
    await _wait_step(temporal_client, wf_id, "service_pick", timeout_s=30.0)

    # 2) pick service (MUST match parse_svc_row_id)
    await signal_booking_workflow(
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id=_eid(), client_id=client_id, kind="list", list_id="svc:haircut"),
        temporal_client=temporal_client,
    )
    await _wait_step(temporal_client, wf_id, "slots_pick", timeout_s=30.0)

    # 3) pick slot (MUST match parse_slot_row_id)
    await signal_booking_workflow(
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id=_eid(), client_id=client_id, kind="list", list_id="slot:haircut-slot-1"),
        temporal_client=temporal_client,
    )
    await _wait_step(temporal_client, wf_id, "confirm", timeout_s=30.0)

    # 4) confirm
    await signal_booking_workflow(
        business_id=business_id,
        client_id=client_id,
        ev=InboundEvent(event_id=_eid(), client_id=client_id, kind="button", button_id="confirm"),
        temporal_client=temporal_client,
    )

    # wait for completion
    result = await temporal_client.get_workflow_handle(wf_id).result()
    print("RESULT:", result)


if __name__ == "__main__":
    asyncio.run(run_happy_path())
