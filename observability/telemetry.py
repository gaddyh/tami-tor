# telemetry.py
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence
from langfuse import propagate_attributes
from observability.langfuse_client import langfuse

from models.input import In  # your Pydantic model
Json = Dict[str, Any]


def _enum_to_str(x: Any) -> Optional[str]:
    if x is None:
        return None
    return str(getattr(x, "value", x))


def _collect_tags(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen = set()
    for v in values:
        s = _enum_to_str(v)
        if s and s.strip() and s not in seen:
            out.append(s.strip())
            seen.add(s)
    return out


def set_common_trace_attrs(
    payload: In,
    *,
    # Which attributes (by name) to turn into tags, in order. Nothing else is touched.
    tag_keys: Sequence[str] = ("source", "category", "locale", "tz"),
    # Which attributes (by name) to copy into metadata (rename via metadata_key_map).
    metadata_keys: Sequence[str] = ("input_id", "idempotency_key"),
    # Rename metadata keys without hard-coding: {"input_id": "input.id", ...}
    metadata_key_map: Mapping[str, str] = {"input_id": "input.id", "idempotency_key": "input.idempotency_key"},
    # Let callers append their own safe metadata explicitly.
    extra_metadata: Optional[Json] = None,
):
    """
    Minimal, generic propagation:
      - requires payload.user_id and payload.thread_id
      - derives tags only from `tag_keys`
      - copies metadata only from `metadata_keys` (renamed via `metadata_key_map`)
      - never serializes the whole payload
    """
    user_id = getattr(payload, "user_id", None)
    thread_id = getattr(payload, "thread_id", None)
    if not user_id or not thread_id:
        raise ValueError("payload must include user_id and thread_id")

    # Tags: only from the keys you asked for.
    tag_values = [getattr(payload, k, None) for k in tag_keys]
    tags = _collect_tags(tag_values)

    # Metadata: only the keys you asked for, optionally renamed.
    meta: Json = {}
    for k in metadata_keys:
        v = getattr(payload, k, None)
        if v is not None:
            meta_name = metadata_key_map.get(k, k)
            meta[meta_name] = v

    if extra_metadata:
        # caller-provided, already deliberate
        meta.update(extra_metadata)

    # Return the context manager from langfuse
    return propagate_attributes(
        user_id=user_id,
        session_id=thread_id,
        tags=tags,
        metadata=meta,
    )


def mark_error(exc: Exception, *, kind: str = "UnhandledError", span=None, extra: Optional[Json] = None) -> None:
    """
    Minimal error marking; no payload dumping. Add explicit `extra` if needed.
    """
    meta = {"status": "error", "error.kind": kind, "error.type": type(exc).__name__}
    if extra:
        meta["error.extra"] = extra

    if span is not None:
        try:
            span.update(metadata=meta)
        except Exception:
            pass

    langfuse.update_current_span(
        metadata=meta,
        status_message=str(exc),
        level="ERROR",
    )
