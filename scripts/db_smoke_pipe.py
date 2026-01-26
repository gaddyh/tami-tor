# scripts/db_smoke_pipe.py
from sqlalchemy import select, func

from db.session import SessionLocal
from models.outbox import Outbox
from models.outbound_message import OutboundMessage
from models.session import Session


def main() -> None:
    with SessionLocal() as db:
        print("---- SESSIONS ----")
        sessions_count = db.scalar(select(func.count()).select_from(Session))
        print(f"Total sessions: {sessions_count}")

        print("\n---- OUTBOX ----")
        by_status = dict(
            db.execute(
                select(Outbox.status, func.count())
                .group_by(Outbox.status)
            ).all()
        )
        for status, count in by_status.items():
            print(f"{status}: {count}")

        total_outbox = sum(by_status.values())
        print(f"Total outbox rows: {total_outbox}")

        print("\n---- OUTBOUND MESSAGES ----")
        outbound_count = db.scalar(
            select(func.count()).select_from(OutboundMessage)
        )
        print(f"Total outbound messages: {outbound_count}")

        print("\n---- SANITY CHECK ----")
        if total_outbox == outbound_count and by_status.get("pending", 0) == 0:
            print("✅ Looks good: no pending jobs, no duplicates detected.")
        else:
            print("⚠️ Check needed:")
            if by_status.get("pending", 0) != 0:
                print(" - There are still pending outbox jobs")
            if total_outbox != outbound_count:
                print(" - Outbox count != outbound messages count")


if __name__ == "__main__":
    main()
