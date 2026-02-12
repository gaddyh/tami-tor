# models/business_provider.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func, UniqueConstraint, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class BusinessProvider(Base):
    __tablename__ = "business_providers"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_business_provider_user_id"),
        Index("business_providers_business_id_idx", "business_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # join by business_id (your stable tenant key)
    business_id: Mapped[str] = mapped_column(String(64), ForeignKey("businesses.business_id"), nullable=False)

    # WhatsApp sender id (phone) or your normalized user id
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)

    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)

    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Jerusalem")
    google_calendar_id: Mapped[str] = mapped_column(String(256), nullable=False, server_default="primary")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # keep provider-specific config flexible
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
