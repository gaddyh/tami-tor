# apps/cron/sweep_scheduled_messages.py
from __future__ import annotations

import json
import time
from typing import List

from sqlalchemy import text

from apps.config import WORK_SWEEP_BATCH, WORK_STALE_SECONDS
from db.session import SessionLocal
from handlers.utility import now_israel

KIND_SCHEDULED_MESSAGE = "SCHEDULED_MESSAGE"


def _select_stale_processing(db) -> List[str]:
    rows = db.execute(
        text(
            """
            SELECT id
            FROM tami_scheduled_messages
            WHERE status = 'processing'
              AND sent_at IS NULL
              AND updated_at < (now() - (:stale_seconds || ' seconds')::interval)
            ORDER BY updated_at ASC
            LIMIT :limit
            """
        ),
        {"stale_seconds": WORK_STALE_SECONDS, "limit": WORK_SWEEP_BATCH},
    ).fetchall()
    return [str(r[0]) for r in rows]


def _reset_processing_to_scheduled(db, ids: List[str]) -> int:
    if not ids:
        return 0
    res = db.execute(
        text(
            """
            UPDATE tami_scheduled_messages
            SET status = 'scheduled',
                updated_at = now()
            WHERE id = ANY(:ids)
              AND status = 'processing'
              AND sent_at IS NULL
            """
        ),
        {"ids": ids},
    )
    return res.rowcount or 0


def _claim_due_scheduled(db) -> List[str]:
    """
    Atomically claim due scheduled messages (scheduled -> processing) and return ids.
    This removes the select-then-update race.
    """
    rows = db.execute(
        text(
            """
            WITH due AS (
                SELECT id
                FROM tami_scheduled_messages
                WHERE status = 'scheduled'
                  AND sent_at IS NULL
                  AND send_at <= now()
                ORDER BY send_at ASC
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            UPDATE tami_scheduled_messages m
            SET status = 'processing',
                updated_at = now()
            FROM due
            WHERE m.id = due.id
            RETURNING m.id
            """
        ),
        {"limit": WORK_SWEEP_BATCH},
    ).fetchall()

    return [str(r[0]) for r in rows]


from models.work_item import WorkItem

def _insert_work_items(db, message_ids: List[str]) -> int:
    """
    Create WorkItem rows pointing at scheduled message rows.
    Uses ORM so work_id default is generated (matches webhook_ingest design).
    """
    if not message_ids:
        return 0

    # Fetch the scheduled messages we claimed (processing) and create work items for them.
    rows = db.execute(
        text(
            """
            SELECT id, wa_id, to_chat_id
            FROM tami_scheduled_messages
            WHERE id = ANY(:ids)
              AND status = 'processing'
              AND sent_at IS NULL
            """
        ),
        {"ids": message_ids},
    ).fetchall()

    created = 0
    for (msg_id, wa_id, to_chat_id) in rows:
        wi = WorkItem(
            kind=KIND_SCHEDULED_MESSAGE,
            ref_id=msg_id,
            business_id=None,           # set if you can derive it from wa_id
            client_id=str(to_chat_id),  # useful for observability / routing
            run_after=None,
        )
        db.add(wi)
        created += 1

    # Ensure work_id values are generated now
    db.flush()
    return created

def sweep_scheduled_messages() -> dict:
    t0 = time.time()

    stale_ids: List[str] = []
    stale_reset = 0

    claimed_ids: List[str] = []
    work_items_created = 0

    db = SessionLocal()
    try:
        stale_ids = _select_stale_processing(db)
        if stale_ids:
            stale_reset = _reset_processing_to_scheduled(db, stale_ids)

        claimed_ids = _claim_due_scheduled(db)
        if claimed_ids:
            work_items_created = _insert_work_items(db, claimed_ids)

        if stale_ids or claimed_ids:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    dt_ms = int((time.time() - t0) * 1000)
    return {
        "ok": True,
        "ts": now_israel().isoformat(),
        "due_claimed": len(claimed_ids),
        "stale_found": len(stale_ids),
        "stale_reset": stale_reset,
        "work_items_created": work_items_created,
        "duration_ms": dt_ms,
        "batch": WORK_SWEEP_BATCH,
        "stale_seconds": WORK_STALE_SECONDS,
        "kind": KIND_SCHEDULED_MESSAGE,
    }


def main() -> None:
    result = sweep_scheduled_messages()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
