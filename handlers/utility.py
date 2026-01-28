
from sqlalchemy import select
from models.session import Session as ChatSession

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
        session.updated_at = datetime.now(timezone.utc)
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
