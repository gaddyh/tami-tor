# apps/cron/sweep_outbox.py
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import List, Tuple

from sqlalchemy import text

from db.session import SessionLocal
from runtime.redis_client import enqueue_outbox, redis_client, QUEUE_OUTBOX

# --- Config (env overridable) ---
OUTBOX_SWEEP_BATCH = int(os.getenv("OUTBOX_SWEEP_BATCH", "500"))
OUTBOX_STALE_SECONDS = int(os.getenv("OUTBOX_STALE_SECONDS", "120"))  # 2 minutes

# Optional: emit events to your Redis Stream (if you already show them in dashboard)
OUTBOX_STREAM_KEY = os.getenv("OUTBOX_STREAM_KEY", "outbox:events")
OUTBOX_EMIT_STREAM = os.getenv("OUTBOX_EMIT_STREAM", "1") == "1"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(event: str, *, outbox_id: str, meta: dict) -> None:
    """
    Best-effort: emits a Redis Stream event for observability.
    Safe to disable via OUTBOX_EMIT_STREAM=0.
    """
    if not OUTBOX_EMIT_STREAM:
        return
    try:
        redis_client.xadd(
            OUTBOX_STREAM_KEY,
            {
                "ts": _utc_iso(),
                "event": event,
                "outbox_id": outbox_id,
                "meta": json.dumps(meta, separators=(",", ":")),
            },
            maxlen=5000,
            approximate=True,
        )
    except Exception:
        # Never fail the cron run because telemetry failed
        pass


def _select_runnable_pending(db) -> List[str]:
    """
    Pending rows that should run now.
    Assumes columns: outbox_id, status, run_after, created_at
    """
    rows = db.execute(
        text(
            """
            SELECT outbox_id
            FROM outbox
            WHERE status = 'pending'
              AND (run_after IS NULL OR run_after <= now())
            ORDER BY created_at ASC
            LIMIT :limit
            """
        ),
        {"limit": OUTBOX_SWEEP_BATCH},
    ).fetchall()

    # rows are tuples unless you configured row mapping
    return [r[0] for r in rows]


def _select_stale_processing(db) -> List[str]:
    """
    Processing rows that look stuck.
    Assumes columns: outbox_id, status, updated_at
    """
    rows = db.execute(
        text(
            """
            SELECT outbox_id
            FROM outbox
            WHERE status = 'processing'
              AND updated_at < (now() - (:stale_seconds || ' seconds')::interval)
            ORDER BY updated_at ASC
            LIMIT :limit
            """
        ),
        {"stale_seconds": OUTBOX_STALE_SECONDS, "limit": OUTBOX_SWEEP_BATCH},
    ).fetchall()

    return [r[0] for r in rows]


def _reset_processing_to_pending(db, outbox_ids: List[str]) -> int:
    """
    Sets stale processing rows back to pending.
    Leaves attempts unchanged (your worker likely increments attempts on claim).
    """
    if not outbox_ids:
        return 0

    res = db.execute(
        text(
            """
            UPDATE outbox
            SET status = 'pending',
                updated_at = now()
            WHERE outbox_id = ANY(:ids)
            """
        ),
        {"ids": outbox_ids},
    )
    return res.rowcount or 0


def sweep_outbox() -> dict:
    t0 = time.time()

    pending_ids: List[str] = []
    stale_ids: List[str] = []
    reset_count = 0
    enqueued = 0

    db = SessionLocal()
    try:
        # 1) Find work
        pending_ids = _select_runnable_pending(db)
        stale_ids = _select_stale_processing(db)

        # 2) Heal stuck processing -> pending (so it can be claimed again)
        if stale_ids:
            reset_count = _reset_processing_to_pending(db, stale_ids)
            db.commit()
        else:
            db.rollback()

    finally:
        db.close()

    # 3) Enqueue (duplicates are fine; worker claim is authoritative)
    # Enqueue stale first (they're older, likely important)
    for oid in stale_ids:
        enqueue_outbox(oid)
        enqueued += 1
        _emit("OUTBOX_REENQUEUED", outbox_id=oid, meta={"reason": "stale_processing", "queue": QUEUE_OUTBOX})

    for oid in pending_ids:
        enqueue_outbox(oid)
        enqueued += 1
        _emit("OUTBOX_REENQUEUED", outbox_id=oid, meta={"reason": "pending_runnable", "queue": QUEUE_OUTBOX})

    dt_ms = int((time.time() - t0) * 1000)
    return {
        "ok": True,
        "ts": _utc_iso(),
        "queue": QUEUE_OUTBOX,
        "pending_found": len(pending_ids),
        "stale_found": len(stale_ids),
        "stale_reset": reset_count,
        "enqueued": enqueued,
        "duration_ms": dt_ms,
        "stale_seconds": OUTBOX_STALE_SECONDS,
        "batch": OUTBOX_SWEEP_BATCH,
    }


def main() -> None:
    result = sweep_outbox()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
