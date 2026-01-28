# models/business_scheduled_message.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class BusinessScheduledMessage(Base):
    __tablename__ = "business_scheduled_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    business_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    wa_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # phone_number_id

    to_chat_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    to_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Store the exact Cloud API payload you will send (list/buttons/text etc.)
    interactive_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # When to send (UTC, tz-aware)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="scheduled", index=True)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
