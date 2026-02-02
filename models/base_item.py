from typing import Optional, Literal
from pydantic import BaseModel


from enum import Enum

class ItemStatus(str, Enum):
    open = "open"
    completed = "completed"
    deleted = "deleted"


class BaseActionItem(BaseModel):
    # Optional for create, required for update/delete (enforced in tool logic)
    item_id: Optional[str] = None

    user_id: Optional[str] = None
    command: Literal["create", "update", "delete"]
    item_type: Literal["scheduled_message", "event"]  # discriminator

    title: Optional[str] = None          # always required semantically
    description: Optional[str] = None

    # Lifecycle status – shared across item types if you want
    status: ItemStatus = "open"

    # Idempotency key
    op_id: Optional[str] = None

    model_config = {"extra": "forbid"}
