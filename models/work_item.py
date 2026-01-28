# models/work_item.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class WorkItem(Base):
    __tablename__ = "work_items"

    work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # What kind of work this is (dispatch key)
    kind: Mapped[str] = mapped_column(Text, nullable=False, index=True)  # e.g. INBOUND, CALENDAR, SCHEDULED

    # Pointer to the domain row (InboundMessage.id / CalendarEvent.id / ScheduledItem.id)
    ref_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # For locks/ordering/visibility; nullable for system jobs
    business_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    client_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
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
