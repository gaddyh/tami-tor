from sqlalchemy.orm import Session

from handlers.errors import NonRetryableError
from models.inbound_message import InboundMessage
from models.work_item import WorkItem


def handle_process_inbound(db: Session, wi: WorkItem) -> None:
    """
    - load inbound message row via wi.ref_id
    - load/create session
    - reduce state
    - emit effects (e.g., create outbound rows / schedule sends)
    """
    if wi.kind != "INBOUND":
        raise NonRetryableError(f"handle_process_inbound got wrong kind: {wi.kind}")

    inbound = db.get(InboundMessage, wi.ref_id)
    if not inbound:
        # If the pointer is broken, retrying won't help.
        raise NonRetryableError(f"InboundMessage not found for ref_id={wi.ref_id}")

    # Now you have the durable row
    raw = inbound.raw or {}
    phone_number_id = inbound.phone_number_id
    from_ = inbound.from_
    message_id = inbound.message_id

    print(
        "Processing inbound work:",
        {"work_id": str(wi.work_id), "ref_id": str(wi.ref_id), "message_id": message_id, "from": from_},
        flush=True,
    )

    # ... next: load/create Session, reduce, emit new work items, etc.
