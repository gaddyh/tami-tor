# runtime/redis_client.py
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from redis import Redis

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
def enqueue_work(work_id: str) -> None:
    if not work_id:
        raise ValueError("work_id is required")
    redis_client.rpush(QUEUE_WORK, work_id)


def dequeue_work(*, block_seconds: int = 10) -> Optional[str]:
    if block_seconds <= 0:
        raise ValueError("block_seconds must be > 0")
    item = redis_client.blpop(QUEUE_WORK, timeout=block_seconds)
    if not item:
        return None
    _, value = item
    return value


# ----------------------------
# Optional legacy helpers
# ----------------------------
def enqueue_inbound(inbound_id: str) -> None:
    """
    Legacy: if you still enqueue inbound directly.
    Preferred: enqueue_work(work_id) where work_items.kind == 'INBOUND'
    """
    if not inbound_id:
        raise ValueError("inbound_id is required")
    redis_client.rpush(QUEUE_INBOUND, inbound_id)


def dequeue_inbound(*, block_seconds: int = 10) -> Optional[str]:
    if block_seconds <= 0:
        raise ValueError("block_seconds must be > 0")
    item = redis_client.blpop(QUEUE_INBOUND, timeout=block_seconds)
    if not item:
        return None
    _, value = item
    return value


def enqueue_outbox(outbox_id: str) -> None:
    """
    Legacy: only if you still have Outbox in the system (e.g. /hello demo).
    """
    if not outbox_id:
        raise ValueError("outbox_id is required")
    redis_client.rpush(QUEUE_OUTBOX, outbox_id)


def dequeue_outbox(*, block_seconds: int = 10) -> Optional[str]:
    if block_seconds <= 0:
        raise ValueError("block_seconds must be > 0")
    item = redis_client.blpop(QUEUE_OUTBOX, timeout=block_seconds)
    if not item:
        return None
    _, value = item
    return value
