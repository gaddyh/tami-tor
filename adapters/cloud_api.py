
from .primitivies import (
    RawMessage, SenderInfo, ContentInfo, MediaInfo, LocationInfo, 
    ButtonReplyInfo, ListReplyInfo, ReplyContextInfo, SharedContactInfo, ReferralInfo
)
from typing import Optional
from dotenv import load_dotenv
load_dotenv(".venv/.env")
import logging
import httpx
logger = logging.getLogger(__name__)
import os

wa_token = os.environ["WHATSAPP_ACCESS_TOKEN"]

class CloudAPIAdapter():
    def __init__(self, phone_number_id: str = None):
        self.access_token = wa_token
        if phone_number_id:
            self.phone_number_id = phone_number_id

    async def _resolve_media_download_url(self, media_id: str) -> str | None:
        """GET /{media_id} -> {'url': ...}; short-lived. Only call when you truly need it."""
        token = getattr(self, "graph_token", None)
        if not token or not media_id:
            return None
        try:
            meta_url = f"https://graph.facebook.com/v16.0/{media_id}"
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(meta_url, headers={"Authorization": f"Bearer {token}"})
                r.raise_for_status()
                return r.json().get("url")
        except Exception:
            logger.exception("Failed to resolve media URL (media_id=%s)", media_id)
            return None

    async def parse_incoming(self, message: dict) -> RawMessage:
        try:
            
            msg_type = message.get("type")
            content = ContentInfo(type=msg_type)

            if msg_type == "text":
                content.text = message.get("text", {}).get("body", "")

            elif msg_type in ["image", "video", "audio", "document"]:
                media = message.get(msg_type, {}) or {}
                media_id = media.get("id")
                mime_type = media.get("mime_type")
                caption = media.get("caption")
                sha256 = media.get("sha256")

                # Keep the metadata endpoint; resolve to actual download URL only when needed.
                media_meta_url = f"https://graph.facebook.com/v16.0/{media_id}" if media_id else None

                content.media = MediaInfo(
                    url=media_meta_url,
                    mime_type=mime_type,
                    caption=caption,
                    sha256=sha256,
                    media_id=media_id
                )

                if media_id:
                    content.media.download_url = await self._resolve_media_download_url(media_id)

            elif msg_type == "location":
                loc = message.get("location", {}) or {}
                content.location = LocationInfo(
                    latitude=float(loc.get("latitude", 0.0)),
                    longitude=float(loc.get("longitude", 0.0)),
                    name=loc.get("name"),
                    address=loc.get("address")
                )

            elif msg_type == "interactive":
                interactive = message.get("interactive", {}) or {}
                itype = interactive.get("type")

                if itype == "button_reply":
                    btn = interactive.get("button_reply", {}) or {}
                    ctx = interactive.get("context", {}) or {}

                    content.button_reply = ButtonReplyInfo(
                        payload=btn.get("id"),          # approve / reject
                        text=btn.get("title"),
                        context_wamid=ctx.get("id")     # << THIS is the BookingApprovalRequest doc id
                    )

                elif itype == "list_reply":
                    lst = interactive.get("list_reply", {}) or {}
                    content.list_reply = ListReplyInfo(
                        payload=lst.get("id"),
                        title=lst.get("title"),
                        description=lst.get("description")
                    )

            elif msg_type == "contacts":
                contact_info = message.get("contacts", [{}])[0]
                name = (contact_info or {}).get("name", {}) or {}
                phones = (contact_info or {}).get("phones", [{}]) or [{}]
                content.contact = SharedContactInfo(
                    formatted_name=name.get("formatted_name", ""),
                    first_name=name.get("first_name"),
                    last_name=name.get("last_name"),
                    phone=phones[0].get("phone") if phones else None
                )

            elif msg_type == "button":
                btn = message.get("button", {}) or {}
                ctx = message.get("context", {}) or {}

                # Template quick replies:
                # - btn.payload is what you configured / or Meta-generated
                # - btn.text is what user sees (כן/לא)
                # - ctx.id is the original template message id (wamid)  ✅ this is your BAR doc id
                content.button_reply = ButtonReplyInfo(
                    payload=btn.get("payload"),      # decision key
                    text=btn.get("text"),            # "כן" / "לא"
                    context_wamid=ctx.get("id")      # wamid of template message
                )


            elif msg_type == "sticker":
                logger.info("Sticker message received — currently unsupported.")
                return None

            else:
                logger.warning(f"Unhandled message type: {msg_type}")
                return None

            # ---- Hydrate quoted reply context from our local index (set in webhook) ----
            ctx = (message or {}).get("context") or {}
            if ctx:
                quoted_id = ctx.get("id")
                quoted_from = ctx.get("from")
                rc = ReplyContextInfo(
                    quoted_message_id=quoted_id,
                    quoted_sender_phone=quoted_from
                )

                if quoted_id:
                    orig = MESSAGE_INDEX.get(quoted_id)
                    if orig:
                        otype = orig.get("type")
                        rc.original_type = otype

                        if otype == "text":
                            rc.original_text = ((orig.get("text") or {}).get("body")
                                                or orig.get("body") or "")
                        elif otype in ("image", "video", "audio", "document"):
                            om = orig.get(otype) or {}
                            omid = om.get("id")
                            rc.original_caption = om.get("caption")
                            rc.original_mime_type = om.get("mime_type")
                            rc.original_media_id = omid
                            # Optional: resolve short-lived download URL (if token present)
                            rc.original_media_url = await self._resolve_media_download_url(omid) if omid else None
                    else:
                        logger.info("Quoted message %s not found in index", quoted_id)

                content.reply_context = rc

            # Optional: referral (ad attribution)
            if "referral" in message:
                ref = message["referral"] or {}
                content.referral = ReferralInfo(
                    source_url=ref.get("source_url"),
                    source_type=ref.get("source_type"),
                    headline=ref.get("headline"),
                    body=ref.get("body"),
                    image_url=ref.get("image_url")
                )

            print("identity", sender)

            return RawMessage(
                sender=sender,
                content=content,
                chat_id=chat_id,
                direction=message_direction,
                message_data=message,
                idempotency_key=message.get("id"),
                wa_id=phone_number_id,
            )

        except Exception:
            logger.exception("Error building MessageState from CloudAPI data")
            raise