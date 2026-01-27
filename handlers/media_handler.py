
from sqlalchemy.orm import Session
from models.inbound_message import InboundMessage

def handle_media(db: Session, message: InboundMessage) -> None:
    pass