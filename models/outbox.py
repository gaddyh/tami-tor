# models/outbox.py
import uuid
from sqlalchemy import Text, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base


class Outbox(Base):
    __tablename__ = "outbox"

    outbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    type: Mapped[str] = mapped_column(Text, nullable=False)

    business_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    payload_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="pending",
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )

    run_after: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
