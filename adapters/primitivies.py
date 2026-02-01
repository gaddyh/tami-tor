from dataclasses import dataclass
from typing import Literal, Optional, Any
from pydantic import BaseModel

@dataclass
class SenderInfo:
    phone: Optional[str]
    name: Optional[str]
    chatId: Optional[str]
    isSelfSender: bool

@dataclass
class SharedContactInfo:
    formatted_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None

@dataclass
class ReferralInfo:
    source_url: str
    source_type: str
    headline: Optional[str] = None
    body: Optional[str] = None
    image_url: Optional[str] = None


@dataclass
class MediaInfo:
    url: Optional[str]            # meta endpoint: https://graph.facebook.com/v16.0/{media_id}
    mime_type: Optional[str]
    caption: Optional[str]
    sha256: Optional[str]
    media_id: Optional[str]
    download_url: Optional[str] = None   # <-- NEW: short-lived direct URL


class Media(BaseModel):
    mimetype: str
    filename: Optional[str] = None
    data: str

@dataclass
class ButtonReplyInfo:
    payload: str          # approve_booking / reject_booking
    text: str
    context_wamid: str    # wamid of the template message


@dataclass
class ReplyContextInfo:
    quoted_message_id: Optional[str]
    quoted_sender_phone: Optional[str]

    # Enriched fields (optional, filled if found in MESSAGE_INDEX)
    original_type: Optional[str] = None       # "text", "image", "video", etc.
    original_text: Optional[str] = None       # text.body if original was text
    original_media_id: Optional[str] = None   # media id (if original was media)
    original_mime_type: Optional[str] = None  # e.g. "image/jpeg"
    original_caption: Optional[str] = None    # caption if any
    original_media_url: Optional[str] = None  # resolved download URL (short-lived!)

@dataclass
class ListReplyInfo:
    payload: str
    title: str
    description: Optional[str] = None

@dataclass
class LocationInfo:
    latitude: float
    longitude: float
    name: Optional[str] = None
    address: Optional[str] = None

ContentType = Literal["text", "image", "video", "audio", "document", "interactive", "contacts", "sticker", "location", "button"] #button in use?

@dataclass
class ContentInfo:
    type: ContentType
    text: Optional[str] = None
    media: Optional[MediaInfo] = None
    location: Optional[LocationInfo] = None
    button_reply: Optional[ButtonReplyInfo] = None
    list_reply: Optional[ListReplyInfo] = None
    reply_context: Optional[ReplyContextInfo] = None
    contact: Optional[SharedContactInfo] = None
    referral: Optional[ReferralInfo] = None

@dataclass
class RawMessage:
    content: ContentInfo
    message_data: Any
    idempotency_key: str
    sender: Optional[SenderInfo] = None
    chat_id: Optional[str] = None
    wa_id: Optional[str] = None