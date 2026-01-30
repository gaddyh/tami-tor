from __future__ import annotations
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
from adapters.primitivies import ButtonReplyInfo, ListReplyInfo
from models.business import Business

# ---- Enums / literals (WhatsApp + internal only for now) ----
class Source(str, Enum):
    WHATSAPP = "whatsapp"
    SYSTEM = "system"
    API = "api"


class Category(str, Enum):
    USER_REQUEST = "user_request"           # direct user instruction in WA chat, message to bot
    INCOMING_MSG = "incoming_msg"           # passive inbound WA message (monitored chat), message from green api
    SCHEDULED_TRIGGER = "scheduled_trigger" # timer/cron fired (internal)

# ---- Provenance (WhatsApp + generic system IDs) ----
class SourceIds(BaseModel):
    # WhatsApp
    whatsapp_msg_id: Optional[str] = None
    whatsapp_chat_id: Optional[str] = None
    whatsapp_sender_id: Optional[str] = None

    # Internal/Scheduler/API (still useful even if WA-only right now)
    job_id: Optional[str] = None
    request_id: Optional[str] = None

# ---- Attachments (kept generic; you can pass WA media refs/URLs) ----
class AttachmentRef(BaseModel):
    kind: Literal["image", "audio", "file", "url"]
    url: Optional[str] = None
    name: Optional[str] = None
    mime: Optional[str] = None
    size_bytes: Optional[int] = None

QuotedKind = Literal["text", "image", "video", "audio", "document", "sticker", "location", "contact", "unknown"]

class ReplyRef(BaseModel):
    parent_message_id: str                         # the quoted/original WA message id
    parent_chat_id: Optional[str] = None           # chat JID if available
    parent_sender_id: Optional[str] = None         # WA user id/JID who sent the parent
    parent_sender_name: Optional[str] = None       # display name if available
    parent_sent_at: Optional[datetime] = None
    parent_kind: QuotedKind = "unknown"            # coarse type
    parent_text_snippet: Optional[str] = None      # short, redacted/snippet form
    parent_has_media: bool = False                 # quick filter for media replies
    is_parent_from_user: Optional[bool] = None     # whether *you* sent the parent


# ---- The input envelope sent to your agent ----
class In(BaseModel):
    user_id: str                    # your internal user
    user_name: str                  # your internal user name
    thread_id: str                  # canonical conversation context
    chat_id: Optional[str] = None   # raw WA chat id (e.g., "9725xxxx@c.us")
    wa_id: Optional[str] = None     # whatsapp bot id
    email: Optional[str] = None     # your internal user email

    source: Optional[Source] = Source.WHATSAPP     # defaults to "whatsapp"
    category: Optional[Category] = None            # defaulted based on text presence

    # Core content (may be empty for pure triggers)
    text: Optional[str] = None

    # Audit & idempotency
    input_id: Optional[str] = None                 # audit primary key (UUID) generated at arrival time
    idempotency_key: Optional[str] = None          # e.g., whatsapp_msg_id, A stable key from the source to prevent double-processing

    # Provenance + extras
    source_ids: Optional[SourceIds] = None
    attachments: List[AttachmentRef] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    reply: Optional[ReplyRef] = None             
    button_reply: Optional[ButtonReplyInfo] = None
    list_reply: Optional[ListReplyInfo] = None

    # Context hints
    locale: Optional[str] = None         # e.g., "he-IL"
    tz: Optional[str] = None             # e.g., "Asia/Jerusalem"
    current_datetime: Optional[str] = None
    # Timing
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Privacy controls
    redacted: bool = False

from enum import Enum

class MessageInputType(str, Enum):
    BTN = "btn"        # button reply
    LIST = "list"      # list reply
    TEXT = "text"      # text or audio-after-transcription
    AUDIO = "audio"    # optional: before transcription

from pydantic import BaseModel, Field
from typing import Optional


class MessageEnvelope(BaseModel):
    # Identity
    inbound_message_id: str = Field(..., description="WhatsApp inbound message id")
    sender_phone: str = Field(..., description="E.164 phone number of sender")

    # Correlation (reply-to outbound)
    context_message_id: Optional[str] = Field(
        None, description="Outbound message id this message replies to (templates / ops)"
    )

    # Classification
    kind: MessageInputType

    is_provider: bool
    # Payload (exactly one should be relevant based on kind)
    button_id: Optional[str] = None
    list_id: Optional[str] = None
    text: Optional[str] = None
    audio_transcript: Optional[str] = None

    # Optional metadata (safe to ignore initially)
    timestamp: Optional[str] = None

class NormalizedInput(BaseModel):
    envelope: MessageEnvelope
    business_id: str

def normalize_input(inp: In, business: Business) -> NormalizedInput:
    # 1) Decide message kind (interactive always wins)
    if inp.button_reply:
        kind = MessageInputType.BTN
    elif inp.list_reply:
        kind = MessageInputType.LIST
    else:
        kind = MessageInputType.TEXT

    # 2) Extract context message id (reply-to outbound)
    context_message_id = None
    if inp.button_reply:
        context_message_id = getattr(inp.button_reply, "context_wamid", None)
    elif inp.list_reply:
        context_message_id = getattr(inp.list_reply, "context_wamid", None)

    # 3) Build envelope
    envelope = MessageEnvelope(
        inbound_message_id=inp.idempotency_key,
        sender_phone=inp.user_id,
        context_message_id=context_message_id,
        kind=kind,
        is_provider=business.is_provider(inp.user_id),
        button_id=inp.button_reply.payload if inp.button_reply else None,
        list_id=inp.list_reply.payload if inp.list_reply else None,
        text=inp.text,
        audio_transcript=None,
        timestamp=inp.current_datetime,
    )

    # 4) Wrap
    return NormalizedInput(
        business_id=business.business_id,
        envelope=envelope,
    )
