# apps/worker.py
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session as OrmSession

from db.session import SessionLocal
from models.inbound_message import InboundMessage

from runtime.redis_client import dequeue_inbound, enqueue_inbound, redis_client
from runtime.events import emit_event
from handlers.registry import INBOUND_HANDLERS
from handlers.errors import NonRetryableError

# Prefer inbound-specific config if you have it; otherwise reuse existing knobs.
from apps.config import INBOUND_QUEUE_NAME, INBOUND_STALE_SECONDS  # type: ignore

# ----------------------------
# Time helpers
# ----------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_seconds(attempt: int) -> int:
    # attempt is 1-based
    return min(2 ** max(0, attempt - 1), 30)


# ----------------------------
# Redis locking (per conversation)
# ----------------------------

LOCK_TTL_SECONDS = int(INBOUND_STALE_SECONDS)

_RELEASE_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
"""


def _lock_key(phone_number_id: str, from_: str) -> str:
    return f"lock:inbound:{phone_number_id}:{from_}"


def acquire_lock(phone_number_id: str, from_: str) -> tuple[bool, str]:
    token = str(uuid.uuid4())
    ok = redis_client.set(
        _lock_key(phone_number_id, from_),
        token,
        nx=True,
        ex=LOCK_TTL_SECONDS,
    )
    return bool(ok), token


def release_lock(phone_number_id: str, from_: str, token: str) -> None:
    try:
        redis_client.eval(_RELEASE_LOCK_LUA, 1, _lock_key(phone_number_id, from_), token)
    except Exception:
        pass


# ----------------------------
# Inbound DB operations
# ----------------------------

def claim_inbound(db: OrmSession, inbound_id: str) -> Optional[InboundMessage]:
    """
    Atomic claim:
    pending -> processing
    increments attempts
    respects run_after
    """
    stmt = text("""
        UPDATE inbound_messages
        SET
            status = 'processing',
            attempts = attempts + 1,
            updated_at = NOW()
        WHERE
            id = :inbound_id
            AND status = 'pending'
            AND (run_after IS NULL OR run_after <= NOW())
        RETURNING id
    """)

    row = db.execute(stmt, {"inbound_id": inbound_id}).mappings().first()
    if not row:
        return None

    inbound = db.get(InboundMessage, row["id"])
    if inbound:
        db.refresh(inbound)
    return inbound


def mark_done(inbound: InboundMessage) -> None:
    inbound.status = "done"
    inbound.last_error = None
    inbound.updated_at = _now_utc()


def mark_failed(inbound: InboundMessage, *, error: str, non_retryable: bool) -> None:
    inbound.status = "failed"
    inbound.last_error = error
    inbound.updated_at = _now_utc()
    # Optionally: stash marker in raw for debugging without a schema change
    try:
        inbound.raw = {**(inbound.raw or {}), "_non_retryable": bool(non_retryable)}
    except Exception:
        pass


def schedule_retry(inbound: InboundMessage, *, error: str) -> datetime:
    delay = _backoff_seconds(int(inbound.attempts))
    run_after = _now_utc() + timedelta(seconds=delay)

    inbound.status = "pending"
    inbound.run_after = run_after
    inbound.last_error = error
    inbound.updated_at = _now_utc()
    return run_after


# ----------------------------
# Handler contract
# ----------------------------

# HANDLERS maps "message kind" -> handler(db, inbound)
# Message kind defaults to inbound.raw["type"] (e.g., "text", "interactive", "image", ...)
Handler = Callable[[OrmSession, InboundMessage], None]


def _inbound_kind(inbound: InboundMessage) -> str:
    raw = inbound.raw or {}
    kind = raw.get("type") or ""
    return kind if isinstance(kind, str) and kind else "unknown"


# ----------------------------
# Worker loop
# ----------------------------

MAX_ATTEMPTS = 5


def main() -> None:
    print("Worker started. Waiting for inbound jobs...", flush=True)

    while True:
        inbound_id = dequeue_inbound(block_seconds=10)
        if not inbound_id:
            continue

        emit_event(
            event="INBOUND_DEQUEUED",
            inbound_id=inbound_id,
            meta={"where": "worker", "queue": INBOUND_QUEUE_NAME},
        )

        claimed: Optional[InboundMessage] = None
        lock_token: Optional[str] = None

        try:
            with SessionLocal() as db:
                claimed = claim_inbound(db, inbound_id)
                if not claimed:
                    continue

                kind = _inbound_kind(claimed)

                emit_event(
                    event="INBOUND_CLAIMED",
                    inbound_id=str(claimed.id),
                    meta={
                        "where": "worker",
                        "kind": kind,
                        "attempt": int(claimed.attempts),
                        "message_id": claimed.message_id,
                        "phone_number_id": claimed.phone_number_id,
                        "from": claimed.from_,
                    },
                )

                acquired, lock_token = acquire_lock(
                    claimed.phone_number_id,
                    claimed.from_,
                )

                if not acquired:
                    run_after = _now_utc() + timedelta(seconds=1)
                    claimed.status = "pending"
                    claimed.run_after = run_after
                    claimed.updated_at = _now_utc()
                    db.commit()

                    emit_event(
                        event="INBOUND_LOCK_MISSED",
                        inbound_id=str(claimed.id),
                        meta={
                            "where": "worker",
                            "phone_number_id": claimed.phone_number_id,
                            "from": claimed.from_,
                            "run_after": run_after.isoformat(),
                        },
                    )

                    enqueue_inbound(str(claimed.id))
                    continue

                emit_event(
                    event="INBOUND_LOCK_ACQUIRED",
                    inbound_id=str(claimed.id),
                    meta={
                        "where": "worker",
                        "phone_number_id": claimed.phone_number_id,
                        "from": claimed.from_,
                    },
                )

                kind = claimed.raw.get("type") or "unknown"

                handler = INBOUND_HANDLERS.get(kind) or INBOUND_HANDLERS.get("*")
                if not handler:
                    mark_failed(
                        claimed,
                        error=f"unknown inbound kind: {kind}",
                        non_retryable=True,
                    )
                    db.commit()

                    emit_event(
                        event="INBOUND_UNKNOWN_KIND",
                        inbound_id=str(claimed.id),
                        meta={
                            "where": "worker",
                            "kind": kind,
                            "message_id": claimed.message_id,
                            "phone_number_id": claimed.phone_number_id,
                            "from": claimed.from_,
                            "attempt": int(claimed.attempts),
                        },
                    )
                    continue

                # Execute handler (no external IO in web; worker can do IO as needed)
                handler(db, claimed)

                mark_done(claimed)
                db.commit()

                emit_event(
                    event="INBOUND_DONE",
                    inbound_id=str(claimed.id),
                    meta={
                        "where": "worker",
                        "kind": kind,
                        "attempt": int(claimed.attempts),
                        "message_id": claimed.message_id,
                        "phone_number_id": claimed.phone_number_id,
                        "from": claimed.from_,
                    },
                )

        except NonRetryableError as e:
            err = str(e)

            emit_event(
                event="INBOUND_FAILED",
                inbound_id=inbound_id,
                meta={"where": "worker", "error": err, "kind": "non_retryable"},
            )

            with SessionLocal() as db:
                m = db.execute(
                    select(InboundMessage).where(InboundMessage.id == inbound_id)
                ).scalar_one_or_none()
                if m and m.status == "processing":
                    mark_failed(m, error=err, non_retryable=True)
                    db.commit()

        except Exception as e:
            err = str(e)

            emit_event(
                event="INBOUND_ERROR",
                inbound_id=inbound_id,
                meta={"where": "worker", "error": err},
            )

            with SessionLocal() as db:
                m = db.execute(
                    select(InboundMessage).where(InboundMessage.id == inbound_id)
                ).scalar_one_or_none()

                if not m or m.status != "processing":
                    pass
                elif int(m.attempts) >= MAX_ATTEMPTS:
                    mark_failed(m, error=err, non_retryable=False)
                    db.commit()

                    emit_event(
                        event="INBOUND_DLQ_MOVED",
                        inbound_id=str(m.id),
                        meta={
                            "where": "worker",
                            "attempt": int(m.attempts),
                            "message_id": m.message_id,
                            "phone_number_id": m.phone_number_id,
                            "from": m.from_,
                            "error": err,
                        },
                    )
                else:
                    run_after = schedule_retry(m, error=err)
                    db.commit()

                    emit_event(
                        event="INBOUND_RETRY_SCHEDULED",
                        inbound_id=str(m.id),
                        meta={
                            "where": "worker",
                            "attempt": int(m.attempts),
                            "run_after": run_after.isoformat(),
                            "message_id": m.message_id,
                            "phone_number_id": m.phone_number_id,
                            "from": m.from_,
                            "error": err,
                        },
                    )

                    enqueue_inbound(str(m.id))

            time.sleep(0.2)

        finally:
            if claimed and lock_token:
                release_lock(
                    claimed.phone_number_id,
                    claimed.from_,
                    lock_token,
                )


if __name__ == "__main__":
    main()
