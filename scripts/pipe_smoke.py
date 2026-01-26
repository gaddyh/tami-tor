# scripts/pipe_smoke.py
from sqlalchemy import select

from db.session import SessionLocal
from models.session import Session
from models.outbox import Outbox


def main() -> None:
    with SessionLocal() as db:
        session = db.execute(
            select(Session)
            .order_by(Session.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        outbox = db.execute(
            select(Outbox)
            .order_by(Outbox.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        print("---- SESSION ----")
        if session:
            print(
                f"session_id={session.session_id} "
                f"business_id={session.business_id} "
                f"client_id={session.client_id} "
                f"status={session.status}"
            )
        else:
            print("No session found")

        print("\n---- OUTBOX ----")
        if outbox:
            print(
                f"outbox_id={outbox.outbox_id} "
                f"type={outbox.type} "
                f"status={outbox.status} "
                f"attempts={outbox.attempts}"
            )
        else:
            print("No outbox found")


if __name__ == "__main__":
    main()
