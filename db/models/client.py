# models/client.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func, UniqueConstraint, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Client(Base):
    __tablename__ = "clients"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_clients_user_id"),  # enforces “each client contact -> one business”
        Index("clients_business_id_idx", "business_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    business_id: Mapped[str] = mapped_column(String(64), ForeignKey("businesses.business_id"), nullable=False)

    # WhatsApp sender id / phone for the client
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)

    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # free-form metadata (tags, notes, risk flags, etc.)
    meta_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
