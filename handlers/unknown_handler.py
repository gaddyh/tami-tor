
from sqlalchemy.orm import Session
from models.inbound_message import InboundMessage

def handle_unknown(db: Session, message: InboundMessage) -> None:
    pass