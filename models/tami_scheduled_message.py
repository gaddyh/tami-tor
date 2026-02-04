from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class TamiScheduledMessage(Base):
    __tablename__ = "tami_scheduled_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    wa_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # phone_number_id

    to_chat_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    to_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="scheduled", index=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # fast due-lookup + ordering
        Index("ix_tami_sched_status_send_at", "status", "send_at"),

        # enforce idempotency (optional but recommended if you rely on it)
        UniqueConstraint("wa_id", "idempotency_key", name="uq_tami_sched_wa_id_idempotency"),
    )
