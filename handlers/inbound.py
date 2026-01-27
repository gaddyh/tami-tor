from sqlalchemy.orm import Session
from models.inbound_message import InboundMessage

def handle_process_inbound(db: Session, message: InboundMessage) -> None:
    """
    - load session
    - reduce state
    - emit new outbox rows
    """
    pass
