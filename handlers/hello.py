from sqlalchemy.orm import Session
from models.outbox import Outbox
from models.outbound_message import OutboundMessage

def handle_hello(db: Session, outbox: Outbox) -> None:
    payload = outbox.payload_json or {}
    text = payload.get("text", "Hello")

    db.add(
        OutboundMessage(
            business_id=outbox.business_id,
            client_id=outbox.client_id,
            session_id=outbox.session_id,
            text=text,
            meta_json={"outbox_id": str(outbox.outbox_id)},
        )
    )
