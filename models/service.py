from typing import Optional
from pydantic import BaseModel, Field, conint

class Service(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)

    duration_min: conint(gt=0, le=480)  # 1–8 hours
    buffer_min: conint(ge=0, le=240) = 0  # optional buffer up to 4h

    price: conint(ge=0)  # integer currency (agorot / cents recommended)
    description: Optional[str] = Field(default=None, max_length=1000)

    is_active: bool = True

    @property
    def total_block_min(self) -> int:
        """Total calendar block including buffer."""
        return self.duration_min + self.buffer_min
