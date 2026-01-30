# runtime/events.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from db.session import SessionLocal
from models.event_log import EventLog
from runtime.redis_client import redis_client
from handlers.utility import now_israel
from observability.langfuse_client import langfuse

STREAM_OUTBOX_EVENTS = "events:work"


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
    ts = now_israel().isoformat()

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



def emit_event_with_langfuse(event: str, meta: dict | None = None, useLangfuse:bool = False) -> None:
    """
    Emit your existing event, and also log to Langfuse:
      - an 'event' observation (keeps metadata)
      - a numeric score (acts like a metric counter)
    """
    meta = meta or {}

    # Your existing event sink
    emit_event(event=event, meta=meta)

    if not useLangfuse:
        return

    # Best-effort Langfuse (never break worker if LF is down/misconfigured)
    try:
        # 1) Event observation (discrete event in trace) :contentReference[oaicite:2]{index=2}
        with langfuse.start_as_current_span(as_type="event", name=event) as span:
            # metadata is the most useful place for your meta payload
            span.update(metadata=meta)

        # 2) Counter-style metric via numeric score :contentReference[oaicite:3]{index=3}
        # Score name convention: "worker.event.<EVENT_NAME>"
        langfuse.score_current_trace(
            name=f"worker.event.{event}",
            value=1.0,
            data_type="NUMERIC",
        )
    except Exception:
        pass