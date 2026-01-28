# apps/cron/sweep_work.py
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import List

from sqlalchemy import text

from apps.config import WORK_SWEEP_BATCH, WORK_STALE_SECONDS, WORK_QUEUE_NAME
from db.session import SessionLocal
from runtime.redis_client import enqueue_work


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _select_runnable_pending(db) -> List[str]:
    """
    Pending work_items that should run now.
    Columns: work_id, status, run_after, created_at
    """
    rows = db.execute(
        text(
            """
            SELECT work_id
            FROM work_items
            WHERE status = 'pending'
              AND (run_after IS NULL OR run_after <= now())
            ORDER BY created_at ASC
            LIMIT :limit
            """
        ),
        {"limit": WORK_SWEEP_BATCH},
    ).fetchall()

    return [str(r[0]) for r in rows]


def _select_stale_processing(db) -> List[str]:
    """
    Processing work_items that look stuck.
    Columns: work_id, status, updated_at
    """
    rows = db.execute(
        text(
            """
            SELECT work_id
            FROM work_items
            WHERE status = 'processing'
              AND updated_at < (now() - (:stale_seconds || ' seconds')::interval)
            ORDER BY updated_at ASC
            LIMIT :limit
            """
        ),
        {"stale_seconds": WORK_STALE_SECONDS, "limit": WORK_SWEEP_BATCH},
    ).fetchall()

    return [str(r[0]) for r in rows]


def _reset_processing_to_pending(db, work_ids: List[str]) -> int:
    """
    Sets stale processing rows back to pending.
    Leaves attempts unchanged (worker increments attempts on claim).
    """
    if not work_ids:
        return 0

    res = db.execute(
        text(
            """
            UPDATE work_items
            SET status = 'pending',
                updated_at = now()
            WHERE work_id = ANY(:ids)
            """
        ),
        {"ids": work_ids},
    )
    return res.rowcount or 0


def sweep_work() -> dict:
    t0 = time.time()

    pending_ids: List[str] = []
    stale_ids: List[str] = []
    reset_count = 0
    enqueued = 0

    db = SessionLocal()
    try:
        pending_ids = _select_runnable_pending(db)
        stale_ids = _select_stale_processing(db)

        if stale_ids:
            reset_count = _reset_processing_to_pending(db, stale_ids)
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    # enqueue stale first (older / stuck)
    for wid in stale_ids:
        enqueue_work(wid)
        enqueued += 1

    for wid in pending_ids:
        enqueue_work(wid)
        enqueued += 1

    dt_ms = int((time.time() - t0) * 1000)
    return {
        "ok": True,
        "ts": _utc_iso(),
        "queue": WORK_QUEUE_NAME,
        "pending_found": len(pending_ids),
        "stale_found": len(stale_ids),
        "stale_reset": reset_count,
        "enqueued": enqueued,
        "duration_ms": dt_ms,
        "stale_seconds": WORK_STALE_SECONDS,
        "batch": WORK_SWEEP_BATCH,
    }


def main() -> None:
    result = sweep_work()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
