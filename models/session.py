# models/session.py
import uuid
from sqlalchemy import Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    business_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="active",
    )

    state_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )

    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
