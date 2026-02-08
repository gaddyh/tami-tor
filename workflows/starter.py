import asyncio
from temporalio.client import Client

from workflows.booking_with_signal import BookingWorkflow, BookingParams, InboundEvent

async def main(*, business_id: str, client_id: str, ev: InboundEvent) -> None:
    client = await Client.connect("localhost:7233")
    wf_id = f"booking:{business_id}:{client_id}"

    params = BookingParams(business_id=business_id, client_id=client_id)

    handle = await client.start_workflow(
        BookingWorkflow.run,
        params,
        id=wf_id,
        task_queue="booking",
        start_signal="on_inbound",
        start_signal_args=[ev],
    )

    # If you want the final result, await it:
    result = await handle.result()
    print(result)

if __name__ == "__main__":
    asyncio.run(
        main(
            business_id="biz_1",
            client_id="client_1",
            ev=InboundEvent(
                event_id="event_1",
                client_id="client_1",
                kind="list",
                list_id="haircut",
            ),
        )
    )
