# apps/worker.py
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from db.session import SessionLocal
from models.work_item import WorkItem
from runtime.redis_client import dequeue_work, enqueue_work, redis_client
from runtime.events import emit_event
from handlers.work_registry import WORK_HANDLERS
from handlers.errors import NonRetryableError
from handlers.utility import now_israel
from observability.obs import span_attrs

from apps.config import WORK_STALE_SECONDS  # reuse your knob as “stale seconds”
LOCK_TTL_SECONDS = int(WORK_STALE_SECONDS)
MAX_ATTEMPTS = 5


def json_safe(v: Any) -> Any:
    """Best-effort JSON-safe conversion for logging/telemetry payloads."""
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    # UUID / Enum / anything else -> string
    return str(v)


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

        emit_event(
            event="WORK_DEQUEUED",
            inbound_id=json_safe(work_id),
            type="WORKER",
            meta={"work_id": json_safe(work_id), "where": "worker"},
        )

        wi: Optional[WorkItem] = None
        lock_token: Optional[str] = None
        business_id: Optional[str] = None
        client_id: Optional[str] = None

        try:
            with SessionLocal() as db:
                wi = claim_work(db, work_id)
                if not wi:
                    continue

                business_id = json_safe(wi.business_id)
                client_id = json_safe(wi.client_id)
                wi_work_id = json_safe(wi.work_id)
                wi_kind = json_safe(wi.kind)
                wi_attempt = int(wi.attempts) if wi.attempts is not None else 0

                with span_attrs(
                    "wa.job",
                    as_type="span",
                    user_id=json_safe(wi.client_id),
                    business_id=business_id,
                    work_id=wi_work_id,
                    kind=wi_kind,
                    attempt=wi_attempt,
                ):
                    emit_event(
                        event="WORK_CLAIMED",
                        inbound_id=wi_work_id,
                        type=wi_kind,
                        business_id=business_id,
                        client_id=client_id,
                        attempt=wi_attempt,
                        meta={
                            "work_id": wi_work_id,
                            "kind": wi_kind,
                        },
                    )

                    # Lock only if we have business/client context
                    if wi.business_id and wi.client_id:
                        acquired, lock_token = acquire_lock(str(wi.business_id), str(wi.client_id))
                        if not acquired:
                            run_after = now_israel() + timedelta(seconds=1)
                            wi.status = "pending"
                            wi.run_after = run_after
                            wi.updated_at = now_israel()
                            db.commit()

                            emit_event(
                                event="LOCK_MISSED",
                                inbound_id=wi_work_id,
                                type=wi_kind,
                                business_id=business_id,
                                client_id=client_id,
                                attempt=wi_attempt,
                                meta={
                                    "work_id": wi_work_id,
                                    "run_after": run_after.isoformat(),
                                },
                            )
                            enqueue_work(str(wi.work_id))
                            continue

                        emit_event(
                            event="LOCK_ACQUIRED",
                            inbound_id=wi_work_id,
                            type=wi_kind,
                            business_id=business_id,
                            client_id=client_id,
                            attempt=wi_attempt,
                            meta={"work_id": wi_work_id},
                        )

                    handler = WORK_HANDLERS.get(wi.kind)
                    if not handler:
                        mark_failed(wi, error=f"unknown work kind: {wi.kind}")
                        db.commit()
                        emit_event(
                            event="WORK_UNKNOWN_KIND",
                            inbound_id=wi_work_id,
                            type=wi_kind,
                            business_id=business_id,
                            client_id=client_id,
                            attempt=wi_attempt,
                            meta={"work_id": wi_work_id, "kind": wi_kind},
                        )
                        continue

                    call_handler(handler, db, wi)

                    mark_done(wi)
                    db.commit()

                    emit_event(
                        event="WORK_DONE",
                        inbound_id=wi_work_id,
                        type=wi_kind,
                        business_id=business_id,
                        client_id=client_id,
                        attempt=wi_attempt,
                        meta={"work_id": wi_work_id, "kind": wi_kind},
                    )

        except NonRetryableError as e:
            err = str(e)
            emit_event(
                event="WORK_FAILED",
                inbound_id=json_safe(work_id),
                type="WORKER",
                meta={"work_id": json_safe(work_id), "error": err, "kind": "non_retryable"},
            )
            with SessionLocal() as db:
                o = db.get(WorkItem, work_id)
                if o and o.status == "processing":
                    mark_failed(o, error=err)
                    db.commit()

        except Exception as e:
            err = str(e)
            emit_event(
                event="WORK_ERROR",
                inbound_id=json_safe(work_id),
                type="WORKER",
                meta={"work_id": json_safe(work_id), "error": err},
            )

            with SessionLocal() as db:
                o = db.get(WorkItem, work_id)
                if not o or o.status != "processing":
                    pass
                elif int(o.attempts) >= MAX_ATTEMPTS:
                    mark_failed(o, error=err)
                    db.commit()
                    emit_event(
                        event="WORK_DLQ",
                        inbound_id=json_safe(work_id),
                        type=json_safe(o.kind) if getattr(o, "kind", None) else "WORKER",
                        business_id=json_safe(o.business_id),
                        client_id=json_safe(o.client_id),
                        attempt=int(o.attempts),
                        meta={"work_id": json_safe(work_id), "error": err},
                    )
                else:
                    run_after = schedule_retry(o, error=err)
                    db.commit()
                    enqueue_work(str(o.work_id))
                    emit_event(
                        event="WORK_RETRY_SCHEDULED",
                        inbound_id=json_safe(work_id),
                        type=json_safe(o.kind) if getattr(o, "kind", None) else "WORKER",
                        business_id=json_safe(o.business_id),
                        client_id=json_safe(o.client_id),
                        attempt=int(o.attempts),
                        meta={
                            "work_id": json_safe(work_id),
                            "run_after": run_after.isoformat(),
                        },
                    )

            time.sleep(0.2)

        finally:
            if lock_token and business_id and client_id:
                release_lock(str(business_id), str(client_id), lock_token)


if __name__ == "__main__":
    main()
