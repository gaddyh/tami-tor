# models/business.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    business_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # You can keep this if you use it to pick a bot personality/agent config
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)

    business_name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Jerusalem")

    booking_policy_mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="owner_confirm")
    enable_digest: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    booking_policy_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    reminder_policy_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    working_hours_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    services_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


Index("businesses_booking_policy_mode_idx", Business.booking_policy_mode)
