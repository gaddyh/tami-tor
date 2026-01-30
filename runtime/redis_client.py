# runtime/redis_client.py
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from redis import Redis
from observability.obs import instrument_io

# Local dev convenience; on Render env vars already exist.
load_dotenv(".venv/.env")

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL is not set (set it in .env or Render env vars).")

# ----------------------------
# Redis client
# ----------------------------
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

# ----------------------------
# Queue keys (LIST)
# ----------------------------
# IMPORTANT:
# - queues are LISTs (RPUSH/BLPOP/LLEN)
# - streams are STREAMs (XADD/XREVRANGE) and must use a different key, e.g. "events:work"
QUEUE_WORK = os.getenv("WORK_QUEUE_NAME", "jobs:work")

# Optional legacy aliases (ONLY keep if old code still calls enqueue_inbound/enqueue_outbox).
# Otherwise delete these to avoid confusion.
QUEUE_INBOUND = os.getenv("INBOUND_QUEUE_NAME", QUEUE_WORK)
QUEUE_OUTBOX = os.getenv("OUTBOX_QUEUE_NAME", "jobs:outbox")  # keep separate if you still have /hello outbox


def _warn_if_stream_key(name: str, value: str) -> None:
    # Prevent the exact bug you hit: using "events:*" as a queue.
    if value.startswith("events:"):
        raise RuntimeError(
            f"{name}={value} looks like a Redis STREAM key. "
            "Queues must be LIST keys, e.g. jobs:work (not events:work)."
        )


_warn_if_stream_key("WORK_QUEUE_NAME", QUEUE_WORK)
_warn_if_stream_key("INBOUND_QUEUE_NAME", QUEUE_INBOUND)
_warn_if_stream_key("OUTBOX_QUEUE_NAME", QUEUE_OUTBOX)


# ----------------------------
# Generic work queue API
# ----------------------------
@instrument_io(
    name="enqueue_work",
    meta={"operation": "enqueue_work"},
    input_fn=lambda work_id: {
        "work_id": work_id,
    },
    output_fn=lambda result: result,
    redact=True,
)
def enqueue_work(work_id: str) -> None:
    if not work_id:
        raise ValueError("work_id is required")
    redis_client.rpush(QUEUE_WORK, work_id)

@instrument_io(
    name="dequeue_work",
    meta={"operation": "dequeue_work"},
    input_fn=lambda block_seconds: {
        "block_seconds": block_seconds,
    },
    output_fn=lambda result: result,
    redact=True,
)
def dequeue_work(*, block_seconds: int = 10) -> Optional[str]:
    if block_seconds <= 0:
        raise ValueError("block_seconds must be > 0")
    item = redis_client.blpop(QUEUE_WORK, timeout=block_seconds)
    if not item:
        return None
    _, value = item
    return value