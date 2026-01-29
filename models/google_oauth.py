# db/models/google_oauth.py

from datetime import datetime
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base  # your declarative base

class GoogleToken(Base):
    __tablename__ = "google_tokens"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)

    token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    token_uri: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_secret: Mapped[str] = mapped_column(Text, nullable=False)

    # Store scopes as a single space-delimited string (what google-auth typically expects)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)

    expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoogleAuthState(Base):
    __tablename__ = "google_auth_state"

    # In your Firestore version, document id == state
    state: Mapped[str] = mapped_column(String(512), primary_key=True)

    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
