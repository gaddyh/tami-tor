from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.tami_scheduled_message import TamiScheduledMessage


def persist_scheduled_message(
    *,
    db: Session,
    wa_id: str,
    to_chat_id: str,
    message: str,
    send_at: datetime,
    type: str,
    to_name: str | None = None,
    idempotency_key: str | None = None,
) -> TamiScheduledMessage:
    """
    Persist a scheduled message.
    Does NOT enqueue or create a WorkItem.
    Safe to call multiple times if idempotency_key is provided.
    """

    row = TamiScheduledMessage(
        wa_id=wa_id,
        to_chat_id=to_chat_id,
        to_name=to_name,
        message=message,
        send_at=send_at,
        type=type,
        idempotency_key=idempotency_key,
        status="scheduled",
    )

    db.add(row)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        # Idempotent retry: fetch existing row
        if idempotency_key:
            existing = (
                db.query(TamiScheduledMessage)
                .filter(
                    TamiScheduledMessage.wa_id == wa_id,
                    TamiScheduledMessage.idempotency_key == idempotency_key,
                )
                .one_or_none()
            )
            if existing:
                return existing

        # Not idempotent or real conflict → rethrow
        raise

    db.refresh(row)
    return row
