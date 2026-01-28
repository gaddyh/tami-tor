# models/business.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, EmailStr, conint

ISODateTime = str  # ISO8601 with timezone

class ReminderPolicy(BaseModel):
    enabled: bool = True
    offset_minutes: List[conint(gt=0, le=10080)] = Field(default_factory=lambda: [1440, 120])


class WorkingHours(BaseModel):
    start: str = "09:00"
    end: str = "17:00"
    weekend_days: List[conint(ge=0, le=6)] = Field(default_factory=lambda: [4, 5])

class Service(BaseModel):
    id: str
    name: str
    duration_min: conint(gt=0, le=480)
    buffer_min: conint(ge=0, le=240) = 0
    description: Optional[str] = None
    is_active: bool = True
    price: int

class Provider(BaseModel):
    """
    A bookable resource (person) with its own calendar.
    V1 can have exactly 1 provider; teams add more.
    """
    provider_id: str
    display_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    specialties: List[str] = Field(default_factory=list)
    timezone: str = "Asia/Jerusalem"
    google_calendar_id: str = "primary"
    is_active: bool = True
    working_hours: Optional[WorkingHours] = None


class Business(Base):
    __tablename__ = "businesses"

    # Internal PK (uuid) so you can rename business_id later without cascading pain
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Public/business key used everywhere else (stable tenant key)
    business_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Routing keys
    wa_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)       # phone_number_id
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)               # internal agent

    business_name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Jerusalem")

    # Commonly-filtered policy as a scalar (optional but useful)
    booking_policy_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="owner_confirm",
    )

    enable_digest: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # Everything else stays JSONB while you iterate
    booking_policy_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    reminder_policy_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    working_hours_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Lists (keep denormalized for now)
    services_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    providers_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    def providers(self) -> List[Provider]:
        """
        Parsed providers (typed).
        Never raises; invalid entries are skipped.
        """
        out: list[Provider] = []
        for raw in self.providers_json or []:
            try:
                out.append(Provider.model_validate(raw))
            except Exception:
                continue
        return out

    def services(self) -> list[Service]:
        out = []
        for raw in self.services_json or []:
            try:
                out.append(Service.model_validate(raw))
            except Exception:
                continue
        return out


    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def is_provider(self, user_id: str) -> bool:
        if not user_id:
            return False
        return any(p.provider_id == user_id for p in self.providers())

    def get_default_provider_id(
        self,
        requested_provider_id: Optional[str] = None,
    ) -> str:
        # explicit override always wins
        if requested_provider_id and self.is_provider(requested_provider_id):
            return requested_provider_id

        active = [p for p in self.providers() if p.is_active]

        if not active:
            raise ValueError(f"No active providers configured for business {self.business_id}")

        # V1 rule: first active provider
        return active[0].provider_id

    def get_provider_by_id(self, provider_id: str) -> Optional[Provider]:
        for p in self.providers():
            if p.provider_id == provider_id:
                return p
        return None

# Helpful indices
Index("businesses_wa_id_idx", Business.wa_id)
Index("businesses_booking_policy_mode_idx", Business.booking_policy_mode)