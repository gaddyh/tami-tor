# models/outbound_message.py
import uuid
from sqlalchemy import Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    business_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    meta_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
