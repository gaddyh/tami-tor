
from sqlalchemy.orm import Session
from models.inbound_message import InboundMessage

def handle_text(db: Session, message: InboundMessage) -> None:
    print(f"Handling text message: {message.phone_number_id}")
    # TODO: Implement text message handling logic
    pass