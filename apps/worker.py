# apps/worker.py
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session as OrmSession

from db.session import SessionLocal
from models.work_item import WorkItem
from runtime.redis_client import dequeue_work, enqueue_work, redis_client
from runtime.events import emit_event_with_langfuse
from handlers.work_registry import WORK_HANDLERS
from handlers.errors import NonRetryableError
from handlers.utility import now_israel
from observability.obs import span_attrs

from apps.config import WORK_STALE_SECONDS  # reuse your knob as “stale seconds”
LOCK_TTL_SECONDS = int(WORK_STALE_SECONDS)
MAX_ATTEMPTS = 5


def _backoff_seconds(attempt: int) -> int:
    return min(2 ** max(0, attempt - 1), 30)


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
    ok = redis_client.set(_lock_key(business_id, client_id), token, nx=True, ex=LOCK_TTL_SECONDS)
    return bool(ok), token

def release_lock(business_id: str, client_id: str, token: str) -> None:
    try:
        redis_client.eval(_RELEASE_LOCK_LUA, 1, _lock_key(business_id, client_id), token)
    except Exception:
        pass

def claim_work(db: OrmSession, work_id: str) -> Optional[WorkItem]:
    stmt = text("""
        UPDATE work_items
        SET
            status = 'processing',
            attempts = attempts + 1,
            updated_at = NOW()
        WHERE
            work_id = :work_id
            AND status = 'pending'
            AND (run_after IS NULL OR run_after <= NOW())
        RETURNING work_id
    """)
    row = db.execute(stmt, {"work_id": work_id}).mappings().first()
    if not row:
        return None
    wi = db.get(WorkItem, row["work_id"])
    if wi:
        db.refresh(wi)
    return wi


def mark_done(wi: WorkItem) -> None:
    wi.status = "done"
    wi.last_error = None
    wi.updated_at = now_israel()


def mark_failed(wi: WorkItem, *, error: str) -> None:
    wi.status = "failed"
    wi.last_error = error
    wi.updated_at = now_israel()


def schedule_retry(wi: WorkItem, *, error: str) -> datetime:
    delay = _backoff_seconds(int(wi.attempts))
    run_after = now_israel() + timedelta(seconds=delay)
    wi.status = "pending"
    wi.run_after = run_after
    wi.last_error = error
    wi.updated_at = now_israel()
    return run_after


import asyncio
import inspect
from typing import Any, Callable

def call_handler(handler: Callable[..., Any], db, wi) -> None:
    """
    Allow handlers to be sync or async.
    Worker is sync, so we drive async handlers to completion.
    """
    if inspect.iscoroutinefunction(handler):
        asyncio.run(handler(db, wi))
    else:
        handler(db, wi)


def main() -> None:
    print("Worker started. Waiting for work...", flush=True)

    while True:
        work_id = dequeue_work(block_seconds=10)
        if not work_id:
            continue

        emit_event_with_langfuse(event="WORK_DEQUEUED", meta={"work_id": work_id, "where": "worker"})

        wi: Optional[WorkItem] = None
        lock_token: Optional[str] = None
        business_id: Optional[str] = None
        client_id: Optional[str] = None

        try:
            with SessionLocal() as db:
                wi = claim_work(db, work_id)
                if not wi:
                    continue

                business_id = wi.business_id
                client_id = wi.client_id

                with span_attrs(
                    "wa.job",
                    as_type="span",
                    user_id=wi.client_id,
                    business_id=wi.business_id,
                    work_id=wi.work_id,
                    kind=wi.kind,
                    attempt=wi.attempts,
                ):
                    emit_event_with_langfuse(
                        event="WORK_CLAIMED",
                        meta={
                            "work_id": str(wi.work_id),
                            "kind": wi.kind,
                            "attempt": int(wi.attempts),
                            "business_id": wi.business_id or "",
                            "client_id": wi.client_id or "",
                        },
                    )

                    # Lock only if we have business/client context
                    if wi.business_id and wi.client_id:
                        acquired, lock_token = acquire_lock(wi.business_id, wi.client_id)
                        if not acquired:
                            run_after = now_israel() + timedelta(seconds=1)
                            wi.status = "pending"
                            wi.run_after = run_after
                            wi.updated_at = now_israel()
                            db.commit()

                            emit_event_with_langfuse(
                                event="LOCK_MISSED",
                                meta={
                                    "work_id": str(wi.work_id),
                                    "business_id": wi.business_id,
                                    "client_id": wi.client_id,
                                    "run_after": run_after.isoformat(),
                                },
                            )
                            enqueue_work(str(wi.work_id))
                            continue

                        emit_event_with_langfuse(
                            event="LOCK_ACQUIRED",
                            meta={"work_id": str(wi.work_id), "business_id": wi.business_id, "client_id": wi.client_id},
                        )

                    handler = WORK_HANDLERS.get(wi.kind)
                    if not handler:
                        mark_failed(wi, error=f"unknown work kind: {wi.kind}")
                        db.commit()
                        emit_event_with_langfuse(event="WORK_UNKNOWN_KIND", meta={"work_id": str(wi.work_id), "kind": wi.kind})
                        continue

                    call_handler(handler, db, wi)

                    mark_done(wi)
                    db.commit()

                    emit_event_with_langfuse(
                        event="WORK_DONE",
                        meta={"work_id": str(wi.work_id), "kind": wi.kind, "attempt": int(wi.attempts)},
                    )

        except NonRetryableError as e:
            err = str(e)
            emit_event_with_langfuse(event="WORK_FAILED", meta={"work_id": work_id, "error": err, "kind": "non_retryable"})
            with SessionLocal() as db:
                o = db.get(WorkItem, work_id)
                if o and o.status == "processing":
                    mark_failed(o, error=err)
                    db.commit()

        except Exception as e:
            err = str(e)
            emit_event_with_langfuse(event="WORK_ERROR", meta={"work_id": work_id, "error": err})

            with SessionLocal() as db:
                o = db.get(WorkItem, work_id)
                if not o or o.status != "processing":
                    pass
                elif int(o.attempts) >= MAX_ATTEMPTS:
                    mark_failed(o, error=err)
                    db.commit()
                    emit_event_with_langfuse(event="WORK_DLQ", meta={"work_id": work_id, "attempt": int(o.attempts), "error": err})
                else:
                    run_after = schedule_retry(o, error=err)
                    db.commit()
                    enqueue_work(str(o.work_id))
                    emit_event_with_langfuse(
                        event="WORK_RETRY_SCHEDULED",
                        meta={"work_id": work_id, "run_after": run_after.isoformat(), "attempt": int(o.attempts)},
                    )

            time.sleep(0.2)

        finally:
            if lock_token and business_id and client_id:
                release_lock(business_id, client_id, lock_token)


if __name__ == "__main__":
    main()
