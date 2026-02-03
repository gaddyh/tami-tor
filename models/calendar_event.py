from __future__ import annotations

import uuid
from datetime import datetime as dt, date as d

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class EventItem(Base):
    __tablename__ = "event_items"

    __table_args__ = (
        # Table is events-only
        CheckConstraint("item_type = 'event'", name="ck_event_items_item_type"),

        # Enum-ish constraints
        CheckConstraint(
            "status IN ('open','completed','deleted')",
            name="ck_event_items_status",
        ),
        CheckConstraint(
            "delete_scope IN ('single','series','this_and_following')",
            name="ck_event_items_delete_scope",
        ),

        # all_day determines which fields are allowed/required
        CheckConstraint(
            """
            (
              all_day = true
              AND date IS NOT NULL
              AND end_date IS NOT NULL
              AND start_at IS NULL
              AND end_at IS NULL
            )
            OR
            (
              all_day = false
              AND start_at IS NOT NULL
              AND end_at IS NOT NULL
              AND date IS NULL
              AND end_date IS NULL
            )
            """,
            name="ck_event_items_time_shape",
        ),

        # End must be after start
        CheckConstraint(
            """
            (all_day = true AND end_date > date)
            OR
            (all_day = false AND end_at > start_at)
            """,
            name="ck_event_items_end_after_start",
        ),

        # Idempotency: unique per user when op_id is present
        Index(
            "ux_event_items_user_op_id",
            "user_id",
            "op_id",
            unique=True,
            postgresql_where=text("op_id IS NOT NULL"),
        ),

        # Prevent duplicate Google event mapping per user
        Index(
            "ux_event_items_user_gcal_event_id",
            "user_id",
            "gcal_event_id",
            unique=True,
            postgresql_where=text("gcal_event_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    op_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    item_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="event",
        index=True,
    )

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="open",
        index=True,
    )

    gcal_event_id: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        index=True,
    )

    allow_conflicts: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )

    # Timed
    start_at: Mapped[dt | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    end_at: Mapped[dt | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)

    # All-day
    date: Mapped[d | None] = mapped_column(Date, nullable=True, index=True)
    end_date: Mapped[d | None] = mapped_column(Date, nullable=True, index=True)
    all_day: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        index=True,
    )

    participants: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    recurrence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reminders: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    delete_scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="single",
        index=True,
    )
    send_updates: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    notify: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )

    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[dt] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[dt] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
