# models/llm_bootstrap.py
from __future__ import annotations

from typing import Literal, Optional, Union
from pydantic import BaseModel, Field


Intent = Literal["CREATE", "UPDATE", "DELETE", "READ", "OTHER"]


class RouterResult(BaseModel):
    intent: Intent
    confidence: float = 0.0


# ---- Per-intent payloads ----

class CreateBootstrap(BaseModel):
    service_name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None


class ReadBootstrap(BaseModel):
    # keep minimal; extend later (date range, status, etc.)
    start_date: str | None = None
    end_date: str | None = None


class DeleteBootstrap(BaseModel):
    booking_id: str | None = None


class UpdatePatch(BaseModel):
    service_name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None


class UpdateBootstrap(BaseModel):
    booking_id: str | None = None
    patch: UpdatePatch = Field(default_factory=UpdatePatch)


# ---- Unified envelope returned by extractor ----
class BookingBootstrap(BaseModel):
    intent: Intent
    payload: Union[CreateBootstrap, ReadBootstrap, DeleteBootstrap, UpdateBootstrap, None] = None

    # makes union deterministic
    model_config = {"extra": "ignore"}
