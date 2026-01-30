# apps/scheduled_message_ingest.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from db.session import SessionLocal
from models.work_item import WorkItem
from models.business_scheduled_message import BusinessScheduledMessage
from runtime.redis_client import enqueue_work
from runtime.events import emit_event
from handlers.utility import now_israel
from observability.obs import instrument_io

@instrument_io(
    name="persist_scheduled_message_and_enqueue",
    meta={"operation": "persist_scheduled_message_and_enqueue"},
    input_fn=lambda business_id, wa_id, client_id, to_chat_id, interactive_payload, workflow_id, send_at, to_name, idempotency_key: {
        "business_id": business_id,
        "wa_id": wa_id,
        "client_id": client_id,
        "to_chat_id": to_chat_id,
        "interactive_payload": interactive_payload,
        "workflow_id": workflow_id,
        "send_at": send_at,
        "to_name": to_name,
        "idempotency_key": idempotency_key,
    },
    output_fn=lambda result: result,
    redact=True
)
def persist_scheduled_message_and_enqueue(
    *,
    business_id: str,
    wa_id: str,                    # phone_number_id
    client_id: str,                # who this is for (your "from"/chat id)
    to_chat_id: str,               # whatsapp destination
    interactive_payload: dict,     # e.g. services_list_payload(rows)
    workflow_id: str,              # usually session_id as str
    send_at: Optional[datetime] = None,
    to_name: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> str:
    """
    Creates:
      - BusinessScheduledMessage row (domain intent)
      - WorkItem(kind="SCHEDULED", ref_id=msg.id)
    Commits, then enqueues work_id.

    Returns:
      work_id (str)
    """
    if not business_id or not wa_id or not client_id or not to_chat_id:
        raise ValueError("business_id, wa_id, client_id, to_chat_id are required")

    if not isinstance(interactive_payload, dict) or not interactive_payload:
        raise ValueError("interactive_payload must be a non-empty dict")

    send_at = send_at or now_israel()

    msg_id = None
    work_id = None

    with SessionLocal() as db:
        msg = BusinessScheduledMessage(
            business_id=business_id,
            wa_id=wa_id,
            to_chat_id=to_chat_id,
            to_name=to_name,
            interactive_payload=interactive_payload,
            send_at=send_at,
            status="scheduled",
            workflow_id=workflow_id,
            idempotency_key=idempotency_key,
        )
        db.add(msg)
        db.flush()  # msg.id
        msg_id = msg.id

        wi = WorkItem(
            kind="SCHEDULED",
            ref_id=msg_id,
            business_id=business_id,
            client_id=client_id,
        )
        db.add(wi)
        db.flush()  # wi.work_id

        work_id = str(wi.work_id)
        db.commit()

    enqueue_work(work_id)

    emit_event(
        event="WORK_ENQUEUED",
        meta={
            "where": "effects",
            "kind": "SCHEDULED",
            "work_id": work_id,
            "scheduled_message_id": str(msg_id),
            "business_id": business_id,
            "client_id": client_id,
            "wa_id": wa_id,
            "to_chat_id": to_chat_id,
            "send_at": send_at.isoformat(),
        },
    )

    return work_id
