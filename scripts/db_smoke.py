# scripts/db_smoke.py
from sqlalchemy import select

from db.session import SessionLocal
from models.user import User


def main() -> None:
    with SessionLocal() as db:
        row = db.execute(select(User).order_by(User.id.desc()).limit(1)).scalar_one_or_none()

        if not row:
            print("No users found in DB.")
            return

        print(f"Latest user: id={row.id} name={row.name} created_at={row.created_at}")


if __name__ == "__main__":
    main()
