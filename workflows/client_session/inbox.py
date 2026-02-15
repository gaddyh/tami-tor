# workflows/client_session/inbox.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class TextInbox:
    initial: Optional[str] = None
    fallback: List[str] = field(default_factory=list)
    cursor: int = 0

    def ingest_text(self, text: str) -> None:
        t = text.strip()
        if not t:
            return
        if self.initial is None:
            self.initial = t
        else:
            self.fallback.append(t)

    def has_next(self) -> bool:
        return self.cursor < len(self.fallback)

    def pop_next(self) -> Optional[str]:
        if not self.has_next():
            return None
        t = self.fallback[self.cursor]
        self.cursor += 1
        return t

    def reset_for_next_op(self) -> None:
        self.initial = None
        self.fallback.clear()
        self.cursor = 0
