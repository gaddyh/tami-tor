# runtime/events.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from db.session import SessionLocal
from models.event_log import EventLog
from runtime.redis_client import redis_client

STREAM_OUTBOX_EVENTS = "events:outbox"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_event(
    *,
    event: str,
    inbound_id: Optional[str] = None,
    type: Optional[str] = None,
    business_id: Optional[str] = None,
    client_id: Optional[str] = None,
    session_id: Optional[str] = None,
    attempt: Optional[int] = None,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    """
    Best-effort dual logging:
    - Postgres: durable audit
    - Redis Stream: realtime tail

    Never raises (visibility must not break the pipeline).
    """
    meta = meta or {}
    ts = _now_iso()

    # 1) Redis Stream (realtime)
    try:
        fields = {
            "ts": ts,
            "event": event,
            "inbound_id": inbound_id or "",
            "type": type or "",
            "business_id": business_id or "",
            "client_id": client_id or "",
            "session_id": session_id or "",
            "attempt": str(attempt) if attempt is not None else "",
            "meta": json.dumps(meta, ensure_ascii=False),
        }
        # keep stream bounded-ish (approx trimming)
        redis_client.xadd(STREAM_OUTBOX_EVENTS, fields, maxlen=10000, approximate=True)
    except Exception:
        pass

    # 2) Postgres (durable)
    try:
        with SessionLocal() as db:
            row = EventLog(
                event=event,
                outbox_id=inbound_id,
                business_id=business_id,
                client_id=client_id,
                session_id=session_id,
                meta_json={"ts": ts, "type": type, "attempt": attempt, **meta},
            )
            db.add(row)
            db.commit()
    except Exception as e:
        print(f"Failed to log event {event}: {e}")
        pass
