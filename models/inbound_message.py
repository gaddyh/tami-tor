from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class InboundMessage(Base):
    __tablename__ = "inbound_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # WhatsApp identifiers
    message_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # WhatsApp sender
    from_: Mapped[str] = mapped_column("from", String(64), nullable=False, index=True)

    # Provider timestamp (often unix seconds as str). Store as int for easy ordering.
    timestamp: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Raw single message object
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Durable “work item” fields (replaces Outbox)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
