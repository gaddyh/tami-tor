# obs.py (Langfuse v3-compatible)
from __future__ import annotations

import time
import inspect
from functools import wraps
from contextlib import contextmanager
from typing import Any, Callable, ParamSpec, TypeVar, Optional, Mapping
from observability.langfuse_client import langfuse

def _agent_meta(inp: In, target_agent: Optional[TargetAgent] = None, **_):
    return {
        "agent": getattr(target_agent, "value", str(target_agent or "unknown")),
        "operation": "route",
    }

def _agent_input(inp: In, target_agent: Optional[TargetAgent] = None, **_):
    return {
        "user_id": inp.user_id,
        "thread_id": inp.thread_id,
        "text": inp.text or "",
        "reply_parent_id": getattr(getattr(inp, "reply", None), "parent_message_id", None),
    }

def _agent_output(out: AgentResult):
    return out  # will be safely dumped

def _dump(obj: Any) -> Any:
    try:
        md = getattr(obj, "model_dump", None)
        if callable(md): return md()
        d = getattr(obj, "dict", None)
        if callable(d): return d()
        return obj
    except Exception:
        return obj

def _maybe_redact(v: Any, *, redact: bool) -> Any:
    if not redact or not isinstance(v, Mapping): return v
    try:
        return {k: ("***" if k in SENSITIVE else val) for k, val in v.items()}
    except Exception:
        return v

P = ParamSpec("P")
T = TypeVar("T")

def _safe_update_current_span(*, metadata: Optional[dict[str, Any]] = None,
                              status_message: Optional[str] = None,
                              level: Optional[str] = None) -> None:
    try:
        langfuse.update_current_span(metadata=metadata or {},
                                     status_message=status_message,
                                     level=level)
    except Exception:
        # Never let observability crash business logic
        pass

def _safe_span_update(span, *, metadata: dict[str, Any]) -> None:
    try:
        span.update(metadata=metadata)
    except Exception:
        pass
def instrument_io(
    *,
    name: str | Callable[..., str],
    meta: Optional[dict] | Callable[..., Mapping[str, Any]] = None,
    input_fn: Optional[Callable[..., Any]] = None,
    output_fn: Optional[Callable[[Any], Any]] = None,
    redact: bool = False,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorate a function so each call becomes a span, with safe input/output logging.
    """
    def deco(fn: Callable[P, T]) -> Callable[P, T]:
        is_async = inspect.iscoroutinefunction(fn)

        def _name(*args, **kwargs) -> str:
            return name(*args, **kwargs) if callable(name) else name

        def _meta(*args, **kwargs) -> Mapping[str, Any]:
            if callable(meta): return dict(meta(*args, **kwargs))
            return dict(meta or {})

        def _extract_trace_attrs(iv: Any) -> tuple[Optional[str], Optional[str]]:
            # Langfuse trace attrs are `user_id` / `session_id` (strings, <=200 chars)
            if not isinstance(iv, dict):
                return None, None
            uid = iv.get("user_id") or iv.get("userId")
            sid = iv.get("session_id") or iv.get("sessionId") or iv.get("thread_id") or iv.get("threadId")
            uid_s = str(uid).strip() if uid is not None else None
            sid_s = str(sid).strip() if sid is not None else None
            if uid_s == "": uid_s = None
            if sid_s == "": sid_s = None
            return uid_s, sid_s

        async def _async(*args: P.args, **kwargs: P.kwargs) -> T:  # type: ignore[misc]
            n = _name(*args, **kwargs)
            t0 = time.perf_counter()
            with langfuse.start_as_current_span(name=n) as s:
                _safe_span_update(s, metadata=_meta(*args, **kwargs))
                try:
                    iv = None
                    uid = None
                    sid = None
                    if input_fn is not None:
                        iv = _dump(input_fn(*args, **kwargs))
                        uid, sid = _extract_trace_attrs(iv)
                        langfuse.update_current_span(input=_maybe_redact(iv, redact=redact))

                    if uid or sid:
                        from langfuse import propagate_attributes  # local import to avoid global coupling
                        with propagate_attributes(user_id=uid, session_id=sid):
                            out = await fn(*args, **kwargs)
                    else:
                        out = await fn(*args, **kwargs)

                    if output_fn is not None:
                        ov = _dump(output_fn(out))
                        langfuse.update_current_span(output=_maybe_redact(ov, redact=redact))
                    _safe_update_current_span(metadata={"status": "ok", "duration.ms": int((time.perf_counter()-t0)*1000)})
                    return out
                except Exception as e:
                    _safe_update_current_span(
                        metadata={"status": "error", "error.kind": type(e).__name__, "duration.ms": int((time.perf_counter()-t0)*1000)},
                        status_message=str(e), level="ERROR"
                    )
                    mark_error(e, kind="InstrumentedIOError", span=s)
                    raise

        def _sync(*args: P.args, **kwargs: P.kwargs) -> T:
            n = _name(*args, **kwargs)
            t0 = time.perf_counter()
            with langfuse.start_as_current_span(name=n) as s:
                _safe_span_update(s, metadata=_meta(*args, **kwargs))
                try:
                    iv = None
                    uid = None
                    sid = None
                    if input_fn is not None:
                        iv = _dump(input_fn(*args, **kwargs))
                        uid, sid = _extract_trace_attrs(iv)
                        langfuse.update_current_span(input=_maybe_redact(iv, redact=redact))

                    if uid or sid:
                        from langfuse import propagate_attributes  # local import to avoid global coupling
                        with propagate_attributes(user_id=uid, session_id=sid):
                            out = fn(*args, **kwargs)
                    else:
                        out = fn(*args, **kwargs)

                    if output_fn is not None:
                        ov = _dump(output_fn(out))
                        langfuse.update_current_span(output=_maybe_redact(ov, redact=redact))
                    _safe_update_current_span(metadata={"status": "ok", "duration.ms": int((time.perf_counter()-t0)*1000)})
                    return out
                except Exception as e:
                    _safe_update_current_span(
                        metadata={"status": "error", "error.kind": type(e).__name__, "duration.ms": int((time.perf_counter()-t0)*1000)},
                        status_message=str(e), level="ERROR"
                    )
                    mark_error(e, kind="InstrumentedIOError", span=s)
                    raise

        return wraps(fn)(_async if is_async else _sync)
    return deco

def instrument(agent: str, operation: str, **defaults: Any) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Example:
      @instrument(agent="tasks", operation="handle", schema_version="tasks.v1")
      def tasks_agent(...): ...
    Works for both sync and async functions.
    """
    def deco(fn: Callable[P, T]) -> Callable[P, T]:
        name = f"{agent}.{operation}"
        base_meta = {"agent": agent, "operation": operation, **defaults}

        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                t0 = time.perf_counter()
                with langfuse.start_as_current_span(name=name) as span:
                    _safe_span_update(span, metadata=base_meta)
                    try:
                        out = await fn(*args, **kwargs)
                        dur_ms = int((time.perf_counter() - t0) * 1000)
                        _safe_update_current_span(metadata={"status": "ok", "duration.ms": dur_ms})
                        return out
                    except Exception as e:
                        dur_ms = int((time.perf_counter() - t0) * 1000)
                        _safe_update_current_span(
                            metadata={"status": "error",
                                      "error.kind": type(e).__name__,
                                      "duration.ms": dur_ms},
                            status_message=str(e),
                            level="ERROR",
                        )
                        raise
            return wrapper  # type: ignore[misc]
        else:
            @wraps(fn)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                t0 = time.perf_counter()
                with langfuse.start_as_current_span(name=name) as span:
                    _safe_span_update(span, metadata=base_meta)
                    try:
                        out = fn(*args, **kwargs)
                        dur_ms = int((time.perf_counter() - t0) * 1000)
                        _safe_update_current_span(metadata={"status": "ok", "duration.ms": dur_ms})
                        return out
                    except Exception as e:
                        dur_ms = int((time.perf_counter() - t0) * 1000)
                        _safe_update_current_span(
                            metadata={"status": "error",
                                      "error.kind": type(e).__name__,
                                      "duration.ms": dur_ms},
                            status_message=str(e),
                            level="ERROR",
                        )
                        raise
            return wrapper  # type: ignore[misc]
    return deco

from langfuse import propagate_attributes
from contextlib import contextmanager
@contextmanager
def span_attrs(name: str, as_type: str = "span", **attrs: Any):
    """
    Lightweight nested observation with fixed metadata.
    For LLM calls, pass as_type="generation" and model="gpt-4o".
    If user_id is provided, it will be propagated at the trace level.
    All other kwargs go into metadata (e.g., kind, intent_id, etc.)
    """
    t0 = time.perf_counter()

    # Pull out special fields that are NOT metadata
    model = attrs.pop("model", None)
    user_id = attrs.pop("user_id", None)
    # Note: 'kind', 'intent_id', etc. stay in attrs and go to metadata

    # If user_id exists, propagate it at trace level
    if user_id is not None:
        with propagate_attributes(user_id=str(user_id)):
            with langfuse.start_as_current_observation(
                name=name,
                as_type=as_type,
                model=model,
            ) as s:
                yield from _handle_span(s, attrs, t0)
    else:
        with langfuse.start_as_current_observation(
            name=name,
            as_type=as_type,
            model=model,
        ) as s:
            yield from _handle_span(s, attrs, t0)


def _handle_span(s, attrs: dict, t0: float):
    """Helper to handle span metadata and timing"""
    # remaining attrs go to metadata
    if attrs:
        _safe_span_update(s, metadata=dict(attrs))

    try:
        yield s
        dur_ms = int((time.perf_counter() - t0) * 1000)
        _safe_span_update(s, metadata={"status": "ok", "duration.ms": dur_ms})
    except Exception as e:
        dur_ms = int((time.perf_counter() - t0) * 1000)
        # Use direct update for status_message and level since _safe_span_update only accepts metadata
        try:
            s.update(
                metadata={
                    "status": "error",
                    "error.kind": type(e).__name__,
                    "duration.ms": dur_ms,
                },
                status_message=str(e),
                level="ERROR",
            )
        except Exception:
            pass
        raise


# obs_io.py
from typing import Any, Optional
from observability.langfuse_client import langfuse

SENSITIVE_FIELDS = {"text", "message", "note", "content", "body"}

def _safe_dump(obj: Any) -> Any:
    try:
        # Pydantic v2
        md = getattr(obj, "model_dump", None)
        if callable(md):
            return md()
        # Pydantic v1
        dict_ = getattr(obj, "dict", None)
        if callable(dict_):
            return dict_()
        return obj
    except Exception:
        return obj

def _redact(val: Any) -> Any:
    if not isinstance(val, dict):
        return val
    try:
        return {k: ("***" if k in SENSITIVE_FIELDS else v) for k, v in val.items()}
    except Exception:
        return val

def safe_update_current_span_io(*, input: Optional[Any] = None,
                                output: Optional[Any] = None,
                                redact: bool = False) -> None:
    try:
        payload = {}
        if input is not None:
            v = _safe_dump(input)
            payload["input"] = _redact(v) if redact else v
        if output is not None:
            v = _safe_dump(output)
            payload["output"] = _redact(v) if redact else v
        if payload:
            langfuse.update_current_span(**payload)
    except Exception:
        pass

# obs_io.py (continued)
from contextlib import contextmanager
from observability.obs import span_attrs  # your file
from observability.telemetry import mark_error

@contextmanager
def span_step(name: str, *, kind: str, redact_input=False, **attrs):
    with span_attrs(name, **attrs) as s:
        try:
            yield s
        except Exception as e:
            # single place to mark + rethrow
            mark_error(e, kind=kind, span=s)
            raise
