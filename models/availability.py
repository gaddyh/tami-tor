
from typing import List, Optional
from pydantic import BaseModel, Field
ISODateTime = str  # ISO8601 with timezone

class TimeSlot(BaseModel):
    start: ISODateTime
    end: ISODateTime

    # Optional denormalized UI fields
    date: Optional[str] = None           # YYYY-MM-DD
    day_name: Optional[str] = None
    start_time: Optional[str] = None     # HH:MM
    end_time: Optional[str] = None       # HH:MM


class SlotChunk(BaseModel):
    chunk_number: int = Field(..., ge=1)
    slots: List[TimeSlot] = Field(default_factory=list)


class ChunkedAvailability(BaseModel):
    total_chunks: int = Field(..., ge=1)
    total_slots: int = Field(..., ge=0)
    chunks: List[SlotChunk] = Field(default_factory=list)
