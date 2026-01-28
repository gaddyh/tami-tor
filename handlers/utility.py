
from sqlalchemy import select
from models.session import Session as ChatSession
from sqlalchemy.orm import Session
from datetime import datetime
from zoneinfo import ZoneInfo
from models.business import Service

def now_israel():
    tz = ZoneInfo("Asia/Jerusalem")
    return datetime.now(tz)

def get_business_id(phone_number_id: str, client_id: str) -> str:
    # TODO: Implement logic to get business_id from phone_number_id
    # This could be a lookup in a phone_number_to_business mapping
    return phone_number_id

from sqlalchemy import select
from models.business import Business

def load_business_by_wa_id(db, phone_number_id: str) -> Business:
    business = db.execute(
        select(Business)
        .where(Business.wa_id == phone_number_id)
        .limit(1)
    ).scalar_one_or_none()

    if not business:
        raise ValueError(f"No business configured for wa_id={phone_number_id}")

    return business


def build_service_rows(services: list[Service]) -> list[dict]:
    return [
        {
            "id": s.id,
            "title": s.name,
            "description": s.description or f"{s.duration_min} דקות · ₪{s.price}",
        }
        for s in services
        if s.is_active
    ]

def load_or_create_session(
    db: Session,
    *,
    business_id: str,
    client_id: str,
) -> ChatSession:
    # 1) Try to load active session
    session = db.execute(
        select(ChatSession)
        .where(ChatSession.business_id == business_id)
        .where(ChatSession.client_id == client_id)
        .where(ChatSession.status == "active")
        .limit(1)
    ).scalar_one_or_none()

    if session:
        session.updated_at = now_israel()
        return session

    # 2) Create new session
    session = ChatSession(
        business_id=business_id,
        client_id=client_id,
        status="active",
        state_json={},  # start clean
    )
    db.add(session)
    db.flush()  # assigns session.session_id

    return session

if __name__ == "__main__":
    print(now_israel())
