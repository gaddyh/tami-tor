# scripts/outbound_smoke.py
from sqlalchemy import select
from db.session import SessionLocal
from models.outbound_message import OutboundMessage


def main() -> None:
    with SessionLocal() as db:
        msg = db.execute(
            select(OutboundMessage).order_by(OutboundMessage.created_at.desc()).limit(1)
        ).scalar_one_or_none()

        if not msg:
            print("No outbound messages found.")
            return

        print(f"Outbound: id={msg.message_id} text={msg.text} created_at={msg.created_at}")


if __name__ == "__main__":
    main()
