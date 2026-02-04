
from sqlalchemy import select
from models.inbound_message import InboundMessage
from models.session import Session as ChatSession
from sqlalchemy.orm import Session
from datetime import datetime
from zoneinfo import ZoneInfo
from models.business import Service
from adapters.primitivies import RawMessage
from handlers.errors import NonRetryableError
from models.inbound_message import InboundMessage
from models.session_state import SessionState
from models.work_item import WorkItem
from adapters.cloud_api import CloudAPIAdapter
from models.business import Business
from runtime.redis_client import enqueue_work
from runtime.events import emit_event
from observability.obs import instrument_io
from adapters.transcribe import transcribe_facebook_audio

def now_israel():
    tz = ZoneInfo("Asia/Jerusalem")
    return datetime.now(tz)

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

def llm_iso_to_utc(iso_str: str) -> datetime:
    """
    LLM ISO datetime (no tz) → UTC datetime
    Assumes input is Israel local time.
    """
    naive = datetime.fromisoformat(iso_str)
    local = naive.replace(tzinfo=ISRAEL_TZ)
    return local.astimezone(timezone.utc)

def parse_datetime(value: str) -> datetime:
    """Parse an ISO-8601 string. Supports trailing 'Z'. Returns a datetime; no timezone normalization here."""
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)
    
def format_date_time_for_template(chosen_start, tz: str):
    # Parse to datetime
    if isinstance(chosen_start, str):
        dt = parse_datetime(chosen_start)
    else:
        dt = chosen_start

    # Convert to business timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    else:
        dt = dt.astimezone(ZoneInfo(tz))

    date_str = dt.strftime("%d/%m/%Y")   # "12/03/2025"
    time_str = dt.strftime("%H:%M")      # "14:30"

    return date_str, time_str

def get_btn_reply_id(msg) -> str | None:
    # adjust to your RawMessage shape
    c = getattr(msg, "content", None)
    lr = getattr(c, "button_reply", None) if c else None
    payload = getattr(lr, "payload", None) if lr else None
    return payload or None

def get_list_reply_id(msg) -> str | None:
    # adjust to your RawMessage shape
    c = getattr(msg, "content", None)
    lr = getattr(c, "list_reply", None) if c else None
    payload = getattr(lr, "payload", None) if lr else None
    return payload or None

def get_business_id(phone_number_id: str, client_id: str) -> str:
    # TODO: Implement logic to get business_id from phone_number_id
    # This could be a lookup in a phone_number_to_business mapping
    return phone_number_id

def load_business_by_wa_id(db, phone_number_id: str) -> Business:
    business = db.execute(
        select(Business)
        .where(Business.wa_id == phone_number_id)
        .limit(1)
    ).scalar_one_or_none()

    if not business:
        raise ValueError(f"No business configured for wa_id={phone_number_id}")

    return business

def load_business_by_id(db, business_id: str) -> Business:
    business = db.execute(
        select(Business)
        .where(Business.business_id == business_id)
        .limit(1)
    ).scalar_one_or_none()

    if not business:
        return load_business_by_wa_id(db, business_id)

    return business

def services_list_payload(rows) -> dict:
    return {
        "type": "list",
        "body": {"text": "באיזה שירות תרצי לבחור?"},
        "action": {"button": "בחירה", "sections": [{"title": "שירותים זמינים", "rows": rows}]},
    }

def create_scheduled_from_send_service_list(
    *,
    db: Session,
    business_id: str,
    client_id: str,
    phone_number_id: str,
    to_phone: str,
    rows: list[dict],
) -> WorkItem:
    payload = services_list_payload(rows)

    wi = WorkItem(
        kind="SCHEDULED",
        business_id=business_id,
        client_id=client_id,
        status="pending",
        attempts=0,
        run_after=now_israel(),  # run ASAP (or set a future time)
        ref_id=None,
        payload_json={
            "action": "SEND_DYNAMIC_LIST",
            "phone_number_id": phone_number_id,
            "to_phone": to_phone,
            "interactive_payload": payload,
            "meta": {"reason": "SEND_SERVICE_LIST"},
        },
    )
    db.add(wi)
    db.flush()     # assigns wi.work_id
    db.commit()    # durable

    enqueue_work(str(wi.work_id))
    return wi

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

def output_fn(result):
    rawMessage, adapter = result
    return {
        "msg": rawMessage.model_dump(),
        "adapter": adapter.phone_number_id,
    }

def handle_media(content):
    if content.type == "audio":
        text = transcribe_facebook_audio(content.media)
        content.type = "text"
        content.text = f"{text}"

@instrument_io(
    name="ingest_inbound",
    meta={"operation": "ingest_inbound"},
    input_fn=lambda inbound, wi: {
        "work_id": str(wi.work_id),
        "ref_id": str(wi.ref_id),
        "business_id": wi.business_id or "",
        "client_id": wi.client_id or "",
        "phone_number_id": inbound.phone_number_id or "",
        "from_": inbound.from_ or "",
        "message_id": inbound.message_id or "",
    },
    output_fn=output_fn,
    redact=True
)
async def ingest_inbound(inbound:InboundMessage, wi:WorkItem):
    raw = inbound.raw or {}
    phone_number_id = inbound.phone_number_id
    from_ = inbound.from_
    message_id = inbound.message_id

    emit_event(
        event="INBOUND_ROW_LOADED",
        inbound_id=str(wi.ref_id),
        type="INBOUND",
        business_id=wi.business_id,
        client_id=wi.client_id,
        meta={
            "work_id": str(wi.work_id),
            "message_id": message_id,
            "from": from_,
            "phone_number_id": phone_number_id,
        },
    )

    adapter = CloudAPIAdapter(phone_number_id)
    rawMessage: RawMessage = await adapter.parse_incoming(raw)

    handle_media(rawMessage.content)

    emit_event(
        event="INBOUND_PARSED",
        inbound_id=str(wi.ref_id),
        type="INBOUND",
        business_id=wi.business_id,
        client_id=wi.client_id,
        meta={
            "work_id": str(wi.work_id),
            "message_id": message_id,
            "msg_type": rawMessage.content.type,
        },
    )

    return (rawMessage, adapter)

@instrument_io(
    name="load_or_create_session",
    meta={"operation": "load_or_create_session"},
    input_fn=lambda db, business_id, client_id: {
        "business_id": business_id,
        "client_id": client_id,
    },
    output_fn=lambda session: {
        "session_id": str(session.session_id),
        "business_id": session.business_id,
        "client_id": session.client_id,
        "state_json": session.state_json,
    },
    redact=True
)
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
