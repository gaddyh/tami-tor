# apps/worker.py
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session as OrmSession

from db.session import SessionLocal
from models.outbox import Outbox
from models.outbound_message import OutboundMessage

from runtime.redis_client import dequeue_outbox, enqueue_outbox, redis_client
from runtime.events import emit_event
from apps.config import (
    OUTBOX_QUEUE_NAME,
    OUTBOX_STALE_SECONDS,
)

# ----------------------------
# Time helpers
# ----------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_seconds(attempt: int) -> int:
    # attempt is 1-based
    return min(2 ** max(0, attempt - 1), 30)


# ----------------------------
# Redis locking (per client)
# ----------------------------

LOCK_TTL_SECONDS = OUTBOX_STALE_SECONDS

_RELEASE_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
"""


def _lock_key(business_id: str, client_id: str) -> str:
    return f"lock:{business_id}:{client_id}"


def acquire_lock(business_id: str, client_id: str) -> tuple[bool, str]:
    token = str(uuid.uuid4())
    ok = redis_client.set(
        _lock_key(business_id, client_id),
        token,
        nx=True,
        ex=LOCK_TTL_SECONDS,
    )
    return bool(ok), token


def release_lock(business_id: str, client_id: str, token: str) -> None:
    try:
        redis_client.eval(
            _RELEASE_LOCK_LUA,
            1,
            _lock_key(business_id, client_id),
            token,
        )
    except Exception:
        pass


# ----------------------------
# Outbox DB operations
# ----------------------------

def claim_outbox(db: OrmSession, outbox_id: str) -> Optional[Outbox]:
    """
    Atomic claim:
    pending -> processing
    increments attempts
    respects run_after
    """
    stmt = text("""
        UPDATE outbox
        SET
            status = 'processing',
            attempts = attempts + 1,
            updated_at = NOW()
        WHERE
            outbox_id = :outbox_id
            AND status = 'pending'
            AND (run_after IS NULL OR run_after <= NOW())
        RETURNING outbox_id
    """)

    row = db.execute(stmt, {"outbox_id": outbox_id}).mappings().first()
    if not row:
        return None

    outbox = db.get(Outbox, row["outbox_id"])
    if outbox:
        db.refresh(outbox)
    return outbox


def mark_done(outbox: Outbox) -> None:
    outbox.status = "done"
    outbox.updated_at = _now_utc()


def mark_failed(outbox: Outbox, *, error: str, non_retryable: bool) -> None:
    payload = dict(outbox.payload_json or {})
    payload["error"] = error
    payload["non_retryable"] = non_retryable
    outbox.payload_json = payload

    outbox.status = "failed"
    outbox.updated_at = _now_utc()


def schedule_retry(outbox: Outbox, *, error: str) -> datetime:
    payload = dict(outbox.payload_json or {})
    payload["last_error"] = error
    outbox.payload_json = payload

    delay = _backoff_seconds(int(outbox.attempts))
    run_after = _now_utc() + timedelta(seconds=delay)

    outbox.status = "pending"
    outbox.run_after = run_after
    outbox.updated_at = _now_utc()
    return run_after


# ----------------------------
# Handler contract
# ----------------------------

class NonRetryableError(RuntimeError):
    pass


Handler = Callable[[OrmSession, Outbox], None]


def handle_hello(db: OrmSession, outbox: Outbox) -> None:
    payload = outbox.payload_json or {}
    text_value = payload.get("text") or "Hello (default)"

    msg = OutboundMessage(
        business_id=outbox.business_id,
        client_id=outbox.client_id,
        session_id=outbox.session_id,
        text=text_value,
        meta_json={
            "source": "worker",
            "outbox_id": str(outbox.outbox_id),
        },
    )
    db.add(msg)


HANDLERS: dict[str, Handler] = {
    "HELLO": handle_hello,
}


# ----------------------------
# Worker loop
# ----------------------------

def main() -> None:
    print("Worker started. Waiting for jobs...", flush=True)

    while True:
        outbox_id = dequeue_outbox(block_seconds=10)
        if not outbox_id:
            continue

        emit_event(
            event="OUTBOX_DEQUEUED",
            outbox_id=outbox_id,
            meta={"where": "worker"},
        )

        claimed: Optional[Outbox] = None
        lock_token: Optional[str] = None

        try:
            with SessionLocal() as db:
                claimed = claim_outbox(db, outbox_id)
                if not claimed:
                    continue

                emit_event(
                    event="OUTBOX_CLAIMED",
                    outbox_id=str(claimed.outbox_id),
                    type=claimed.type,
                    business_id=claimed.business_id,
                    client_id=claimed.client_id,
                    session_id=str(claimed.session_id),
                    attempt=int(claimed.attempts),
                )

                acquired, lock_token = acquire_lock(
                    claimed.business_id,
                    claimed.client_id,
                )

                if not acquired:
                    run_after = _now_utc() + timedelta(seconds=1)
                    claimed.status = "pending"
                    claimed.run_after = run_after
                    claimed.updated_at = _now_utc()
                    db.commit()

                    emit_event(
                        event="LOCK_MISSED",
                        outbox_id=str(claimed.outbox_id),
                        type=claimed.type,
                        business_id=claimed.business_id,
                        client_id=claimed.client_id,
                        session_id=str(claimed.session_id),
                        attempt=int(claimed.attempts),
                        meta={"run_after": run_after.isoformat()},
                    )

                    enqueue_outbox(str(claimed.outbox_id))
                    continue

                emit_event(
                    event="LOCK_ACQUIRED",
                    outbox_id=str(claimed.outbox_id),
                    type=claimed.type,
                    business_id=claimed.business_id,
                    client_id=claimed.client_id,
                    session_id=str(claimed.session_id),
                    attempt=int(claimed.attempts),
                )

                handler = HANDLERS.get(claimed.type)
                if not handler:
                    mark_failed(
                        claimed,
                        error=f"unknown outbox type: {claimed.type}",
                        non_retryable=True,
                    )
                    db.commit()

                    emit_event(
                        event="OUTBOX_UNKNOWN_TYPE",
                        outbox_id=str(claimed.outbox_id),
                        type=claimed.type,
                        business_id=claimed.business_id,
                        client_id=claimed.client_id,
                        session_id=str(claimed.session_id),
                        attempt=int(claimed.attempts),
                    )
                    continue

                handler(db, claimed)
                mark_done(claimed)
                db.commit()

                emit_event(
                    event="OUTBOX_DONE",
                    outbox_id=str(claimed.outbox_id),
                    type=claimed.type,
                    business_id=claimed.business_id,
                    client_id=claimed.client_id,
                    session_id=str(claimed.session_id),
                    attempt=int(claimed.attempts),
                )

        except NonRetryableError as e:
            with SessionLocal() as db:
                o = db.execute(
                    select(Outbox).where(Outbox.outbox_id == outbox_id)
                ).scalar_one_or_none()
                if o and o.status == "processing":
                    mark_failed(o, error=str(e), non_retryable=True)
                    db.commit()

        except Exception as e:
            err = str(e)

            emit_event(
                event="OUTBOX_FAILED",
                outbox_id=outbox_id,
                meta={"error": err},
            )

            with SessionLocal() as db:
                o = db.execute(
                    select(Outbox).where(Outbox.outbox_id == outbox_id)
                ).scalar_one_or_none()
                if not o or o.status != "processing":
                    pass
                elif int(o.attempts) >= 5:
                    mark_failed(o, error=err, non_retryable=False)
                    db.commit()

                    emit_event(
                        event="DLQ_MOVED",
                        outbox_id=str(o.outbox_id),
                        type=o.type,
                        business_id=o.business_id,
                        client_id=o.client_id,
                        session_id=str(o.session_id),
                        attempt=int(o.attempts),
                    )
                else:
                    run_after = schedule_retry(o, error=err)
                    db.commit()

                    emit_event(
                        event="OUTBOX_RETRY_SCHEDULED",
                        outbox_id=str(o.outbox_id),
                        type=o.type,
                        business_id=o.business_id,
                        client_id=o.client_id,
                        session_id=str(o.session_id),
                        attempt=int(o.attempts),
                        meta={"run_after": run_after.isoformat()},
                    )

                    enqueue_outbox(str(o.outbox_id))

            time.sleep(0.2)

        finally:
            if claimed and lock_token:
                release_lock(
                    claimed.business_id,
                    claimed.client_id,
                    lock_token,
                )


if __name__ == "__main__":
    main()
