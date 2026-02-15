# models/service.py
from pydantic import BaseModel


class Service(BaseModel):
    id: str
    name: str
    price: int
    duration_min: int
    buffer_min: int = 0
    description: str | None = None
    is_active: bool = True
