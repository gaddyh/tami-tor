# runtime/redis_client.py
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from redis import Redis

# Load .env locally; on Render, env vars already exist.
load_dotenv(".venv/.env")

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL is not set (set it in .env or Render env vars).")

QUEUE_OUTBOX = "jobs:outbox"

# One shared client instance per process
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)


def enqueue_outbox(outbox_id: str) -> None:
    """
    Push an outbox_id into the queue.
    Payload is only the outbox_id string (no JSON).
    """
    if not outbox_id:
        raise ValueError("outbox_id is required")
    redis_client.rpush(QUEUE_OUTBOX, outbox_id)


def dequeue_outbox(*, block_seconds: int = 10) -> Optional[str]:
    """
    Blocking pop from the outbox queue.
    Returns outbox_id or None on timeout.
    """
    if block_seconds <= 0:
        raise ValueError("block_seconds must be > 0")

    item = redis_client.blpop(QUEUE_OUTBOX, timeout=block_seconds)
    if not item:
        return None

    # item is (queue_name, value)
    _, value = item
    return value
