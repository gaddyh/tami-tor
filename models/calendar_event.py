from __future__ import annotations

import uuid
from datetime import datetime, date

from sqlalchemy import Boolean, Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class EventItem(Base):
    __tablename__ = "event_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    op_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    item_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="event", index=True)

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open", index=True)

    gcal_event_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)

    allow_conflicts: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # timed (names match your Pydantic)
    datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)

    # all-day
    date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", index=True)

    participants: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    recurrence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reminders: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    delete_scope: Mapped[str] = mapped_column(String(32), nullable=False, server_default="single", index=True)
    send_updates: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notify: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, index=True
    )
