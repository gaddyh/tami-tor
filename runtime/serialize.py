# runtime/serialize.py
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def to_jsonable(obj: Any) -> Any:
    """
    Convert dataclasses (and nested dataclasses) into dicts/lists.
    Leaves basic JSON types unchanged.
    """
    if is_dataclass(obj):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    return obj
