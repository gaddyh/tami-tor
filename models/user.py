# models/user.py
from sqlalchemy import BigInteger, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
