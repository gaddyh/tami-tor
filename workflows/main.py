from workflows.booking_with_signal import BookingWorkflow, BookingParams, InboundEvent
from temporalio.client import Client

TASK_QUEUE = "booking"

async def signal_booking_workflow(
    *,
    business_id: str,
    client_id: str,
    ev: InboundEvent,
    temporal_client: Client,
):
    assert temporal_client is not None, "Temporal client not initialized"

    wf_id = f"booking:{business_id}:{client_id}"

    params = BookingParams(business_id=business_id, client_id=client_id)

    await temporal_client.start_workflow(
        BookingWorkflow.run,
        params,
        id=wf_id,
        task_queue=TASK_QUEUE,
        start_signal="on_inbound",
        start_signal_args=[ev],
    )
