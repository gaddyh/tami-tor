# apps/worker.py
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from db.session import SessionLocal
from models.outbox import Outbox
from models.outbound_message import OutboundMessage
from runtime.redis_client import dequeue_outbox, enqueue_outbox


def _now_utc():
    return datetime.now(timezone.utc)


from sqlalchemy import text

def claim_outbox(db: OrmSession, outbox_id: str) -> Outbox | None:
    """
    Atomic claim:
    - update row from pending -> processing only if it's eligible
    - return the claimed row in the same statement
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
        RETURNING
            outbox_id, type, business_id, client_id, session_id, payload_json,
            status, attempts, run_after, created_at, updated_at
    """)

    row = db.execute(stmt, {"outbox_id": outbox_id}).mappings().first()
    if not row:
        return None

    # Re-hydrate into ORM object (simple approach)
    outbox = db.get(Outbox, row["outbox_id"])
    return outbox


def handle_hello(db: OrmSession, outbox: Outbox) -> None:
    text = (outbox.payload_json or {}).get("text") or "Hello (default)"

    msg = OutboundMessage(
        business_id=outbox.business_id,
        client_id=outbox.client_id,
        session_id=outbox.session_id,
        text=text,
        meta_json={"source": "worker", "outbox_id": str(outbox.outbox_id)},
    )
    db.add(msg)

    outbox.status = "done"
    outbox.updated_at = _now_utc()
    db.commit()


def main() -> None:
    print("Worker started. Waiting for jobs...", flush=True)

    while True:
        outbox_id = dequeue_outbox(block_seconds=10)
        if not outbox_id:
            continue
        
        print(f"Dequeued outbox_id={outbox_id}", flush=True)

        try:
            with SessionLocal() as db:
                outbox = claim_outbox(db, outbox_id)
                if not outbox:
                    continue

                if outbox.type == "HELLO":
                    handle_hello(db, outbox)
                else:
                    # unknown job type -> mark failed (minimal)
                    outbox.status = "failed"
                    outbox.updated_at = _now_utc()
                    outbox.payload_json = {**(outbox.payload_json or {}), "error": "unknown job type"}
                    db.commit()

        except Exception as e:
            # minimal retry: put back as pending with short delay
            print(f"Job failed outbox_id={outbox_id}: {e}")
            with SessionLocal() as db:
                o = db.execute(select(Outbox).where(Outbox.outbox_id == outbox_id)).scalar_one_or_none()
                if o and o.status == "processing":
                    o.status = "pending"
                    o.run_after = _now_utc()  # you can add backoff later
                    o.updated_at = _now_utc()
                    db.commit()
            # re-enqueue so it can retry
            enqueue_outbox(outbox_id)
            time.sleep(0.2)


if __name__ == "__main__":
    main()
