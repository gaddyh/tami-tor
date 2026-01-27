# apps/cron/sweep_inbound.py
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from sqlalchemy import text

from db.session import SessionLocal
from runtime.redis_client import enqueue_inbound, QUEUE_INBOUND

BATCH = int(os.getenv("INBOUND_SWEEP_BATCH", "500"))
STALE_SECONDS = int(os.getenv("INBOUND_STALE_SECONDS", "120"))

def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def main() -> None:
    t0 = time.time()
    db = SessionLocal()

    pending_ids = []
    stale_ids = []
    reset = 0

    try:
        pending_ids = [
            r[0] for r in db.execute(
                text("""
                    SELECT id
                    FROM inbound_messages
                    WHERE status='pending'
                      AND (run_after IS NULL OR run_after <= now())
                    ORDER BY created_at ASC
                    LIMIT :limit
                """),
                {"limit": BATCH},
            ).fetchall()
        ]

        stale_ids = [
            r[0] for r in db.execute(
                text("""
                    SELECT id
                    FROM inbound_messages
                    WHERE status='processing'
                      AND updated_at < (now() - (:stale || ' seconds')::interval)
                    ORDER BY updated_at ASC
                    LIMIT :limit
                """),
                {"stale": STALE_SECONDS, "limit": BATCH},
            ).fetchall()
        ]

        if stale_ids:
            res = db.execute(
                text("""
                    UPDATE inbound_messages
                    SET status='pending', updated_at=now()
                    WHERE id = ANY(:ids)
                """),
                {"ids": stale_ids},
            )
            reset = res.rowcount or 0
            db.commit()
        else:
            db.rollback()

    finally:
        db.close()

    # enqueue (duplicates ok because worker claim is authoritative)
    enq = 0
    for mid in stale_ids:
        enqueue_inbound(str(mid))
        enq += 1
    for mid in pending_ids:
        enqueue_inbound(str(mid))
        enq += 1

    out = {
        "ok": True,
        "ts": utc_iso(),
        "queue": QUEUE_INBOUND,
        "pending_found": len(pending_ids),
        "stale_found": len(stale_ids),
        "stale_reset": reset,
        "enqueued": enq,
        "duration_ms": int((time.time() - t0) * 1000),
        "stale_seconds": STALE_SECONDS,
        "batch": BATCH,
    }
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
