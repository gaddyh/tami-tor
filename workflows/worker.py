import asyncio
import signal

from temporalio.client import Client
from temporalio.worker import Worker

from workflows.client_session import ClientSessionWorkflow
from workflows.provider_session import ProviderWorkflow
from workflows.activities import (
    load_services,
    compute_slots,
    send_text,
    send_services_list,
    send_slots_list,
    send_confirm_buttons,
    create_booking,
)
from workflows.main import TASK_QUEUE

async def main():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ClientSessionWorkflow],
        activities=[
            load_services,
            compute_slots,
            send_text,
            send_services_list,
            send_slots_list,
            send_confirm_buttons,
            create_booking,
        ],
    )

    stop_evt = asyncio.Event()

    def _stop(*_):
        stop_evt.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            # Windows fallback
            signal.signal(sig, lambda *_: _stop())

    print(f"Worker running on task queue: {TASK_QUEUE}")

    worker_task = asyncio.create_task(worker.run())
    await stop_evt.wait()

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
