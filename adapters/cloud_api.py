
from .primitivies import (
    RawMessage, SenderInfo, ContentInfo, MediaInfo, LocationInfo, 
    ButtonReplyInfo, ListReplyInfo, ReplyContextInfo, SharedContactInfo, ReferralInfo
)
from typing import Optional, Dict, Any
from dotenv import load_dotenv
load_dotenv(".venv/.env")
import logging
import httpx
logger = logging.getLogger(__name__)
import os
import uuid

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

            return RawMessage(
                content=content,
                message_data=message,
                idempotency_key=message.get("id"),
            )

        except Exception:
            logger.exception("Error building MessageState from CloudAPI data")
            raise


    from observability.obs import instrument_io
    @instrument_io(
            name="send_message",
            meta={"operation": "send_message"},
            input_fn=lambda self, to_phone, interactive_payload: {
                "to_phone": to_phone,
                "interactive_payload": interactive_payload,
            },
            output_fn=lambda result: result,
            redact=True
        )
    async def send_message(self, recipient: str, message: str, reply_to: str | None = None) -> dict:
        print("Sending message to", recipient, "with message:", message)

        url = f"https://graph.facebook.com/v16.0/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient.replace("@c.us", ""),
            "type": "text",
            "text": {"body": message}
        }

        if reply_to:
            payload["context"] = {"message_id": reply_to}   
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            return {"status": "sent", "response": response.json()}
        else:
            logger.error(f"Failed to send message: {response.status_code} - {response.text}")
            return {"status": "failed", "error": response.text}


    @instrument_io(
        name="send_dynamic_list_message",
        meta={"operation": "send_dynamic_list_message"},
        input_fn=lambda self, to_phone, interactive_payload: {
            "to_phone": to_phone,
            "interactive_payload": interactive_payload,
        },
        output_fn=lambda result: result,
        redact=True
    )
    async def send_dynamic_list_message(
        self,
        *,
        to_phone: str,
        interactive_payload: Dict[str, Any],
        reply_to: Optional[str] = None,
        graph_version: str = "v22.0",
        timeout_s: float = 20.0,
    ) -> Dict[str, Any]:
        """
        Sends a WhatsApp Cloud API *interactive list* message.

        Params:
        - interactive_payload: the value for the "interactive" field (must include {"type":"list", ...})
        - reply_to: optional message_id to reply to (sets payload["context"])
        """
        if not isinstance(interactive_payload, dict):
            raise TypeError("interactive_payload must be a dict")

        # Minimal sanity checks (doesn't validate full schema)
        itype = interactive_payload.get("type")
        if itype != "list":
            raise ValueError(f'interactive_payload["type"] must be "list" (got {itype!r})')

        url = f"https://graph.facebook.com/{graph_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": str(to_phone),
            "type": "interactive",
            "interactive": interactive_payload,
        }

        if reply_to:
            payload["context"] = {"message_id": reply_to}

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if 200 <= resp.status_code < 300:
            return {"status": "sent", "response": resp.json()}

        # Include request payload to help debug quickly (you can remove if sensitive)
        logger.error(
            "Failed to send list message: %s - %s",
            resp.status_code,
            resp.text,
        )
        return {
            "status": "failed",
            "code": resp.status_code,
            "error": resp.text,
            "request": payload,
        }

    @instrument_io(
        name="send_action_buttons",
        meta={"operation": "send_action_buttons"},
        input_fn=lambda self, recipient, message: {
            "recipient": recipient,
            "message": message,
        },
        output_fn=lambda result: result,
        redact=True
    )
    async def send_action_buttons(
            self,
            recipient: str,
            message: str,
            reply_to: str | None = None,
        ) -> dict:
            print("Sending buttons message to", recipient, "with message:", message)

            action_id = f"act_{uuid.uuid4().hex[:8]}"

            url = f"https://graph.facebook.com/v16.0/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            payload = {
                "messaging_product": "whatsapp",
                "to": recipient.replace("@c.us", ""),
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": message
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": f"{action_id}_confirm",
                                    "title": "אשר"
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": f"{action_id}_new_time",
                                    "title": "שנה זמן"
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": f"{action_id}_new_service",
                                    "title": "שנה שירות"
                                }
                            },
                        ]
                    }
                }
            }

            if reply_to:
                payload["context"] = {"message_id": reply_to}

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                return {"status": "sent", "response": response.json()}
            else:
                logger.error(f"Failed to send buttons: {response.status_code} - {response.text}")
                return {"status": "failed", "error": response.text}