# models/user_route.py

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Boolean, func, UniqueConstraint, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class UserRoute(Base):
    """
    O(1) routing table:
    user_id -> (business_id, is_provider)
    """

    __tablename__ = "user_routes"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_routes_user_id"),
        Index("user_routes_business_id_idx", "business_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )

    business_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("businesses.business_id"),
        nullable=False,
    )

    # True => provider workflow
    # False => client workflow
    is_provider: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
