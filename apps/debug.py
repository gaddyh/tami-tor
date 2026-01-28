from fastapi import HTTPException, Header
from fastapi.responses import HTMLResponse
from markupsafe import escape
import os
import json

from sqlalchemy import select, func

from db.session import SessionLocal
from runtime.redis_client import redis_client, QUEUE_WORK
from apps.config import WORK_STREAM_KEY
from models.work_item import WorkItem
from models.inbound_message import InboundMessage


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _compact_json(x, limit: int = 280) -> str:
    try:
        s = json.dumps(x, ensure_ascii=False)
    except Exception:
        s = str(x)
    if len(s) > limit:
        return s[:limit] + "…"
    return s


# -----------------------------
# /debug/state
# -----------------------------
def debug_state(
    count: int = 10,
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    expected = os.getenv("DEBUG_TOKEN")
    if not expected or x_debug_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")

    count = _clamp(count, 1, 100)

    # --- Redis ---
    redis_queue_len = None
    redis_stream = []
    redis_errors = []

    stream_name = os.getenv("WORK_STREAM_KEY", WORK_STREAM_KEY)

    try:
        redis_queue_len = redis_client.llen(QUEUE_WORK)
    except Exception as e:
        redis_errors.append(f"queue_len: {e}")

    try:
        entries = redis_client.xrevrange(stream_name, max="+", min="-", count=count)
        for entry_id, fields in entries:
            # meta is stored as json string in your emitter
            meta = fields.get("meta")
            if meta:
                try:
                    fields["meta"] = json.loads(meta)
                except Exception:
                    pass
            redis_stream.append({"id": entry_id, "fields": fields})
    except Exception as e:
        redis_errors.append(f"stream_tail: {e}")

    # --- Postgres ---
    with SessionLocal() as db:
        # WorkItem status counts
        work_by_status = dict(
            db.execute(
                select(WorkItem.status, func.count()).group_by(WorkItem.status)
            ).all()
        )

        latest_work = db.execute(
            select(WorkItem)
            .order_by(WorkItem.updated_at.desc())
            .limit(20)
        ).scalars().all()

        latest_work_payload = [
            {
                "work_id": str(w.work_id),
                "kind": w.kind,
                "ref_id": str(w.ref_id) if w.ref_id else None,
                "status": w.status,
                "attempts": int(w.attempts),
                "business_id": w.business_id,
                "client_id": w.client_id,
                "run_after": w.run_after.isoformat() if w.run_after else None,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
                "created_at": w.created_at.isoformat() if w.created_at else None,
                "last_error": w.last_error,
            }
            for w in latest_work
        ]

        # InboundMessage: NO status/attempts/run_after/last_error here
        latest_inbound = db.execute(
            select(InboundMessage)
            .order_by(InboundMessage.created_at.desc())
            .limit(20)
        ).scalars().all()

        latest_inbound_payload = [
            {
                "id": str(m.id),
                "message_id": m.message_id,
                "phone_number_id": m.phone_number_id,
                "from": m.from_,
                "timestamp": int(m.timestamp) if m.timestamp is not None else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                # useful for quick debugging without dumping the whole thing
                "raw_preview": _compact_json(m.raw, limit=240),
            }
            for m in latest_inbound
        ]

    return {
        "postgres": {
            "work_by_status": work_by_status,
            "latest_work": latest_work_payload,
            "latest_inbound": latest_inbound_payload,
        },
        "redis": {
            "queue": {"name": QUEUE_WORK, "length": redis_queue_len},
            "stream": {"name": stream_name, "latest": redis_stream},
            "errors": redis_errors,
        },
    }


# -----------------------------
# /debug/ui
# -----------------------------
def debug_ui(token: str, count: int = 20):
    expected = os.getenv("DEBUG_TOKEN")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")

    data = debug_state(count=count, x_debug_token=expected)
    pg = data.get("postgres", {})
    rd = data.get("redis", {})

    def td(x): return f"<td>{escape(str(x))}</td>"
    def th(x): return f"<th>{escape(str(x))}</th>"

    # Redis cards
    queue = rd.get("queue", {}) or {}
    queue_name = queue.get("name") or "?"
    queue_len = queue.get("length", "?")
    redis_errs = "<br/>".join(escape(x) for x in (rd.get("errors") or [])) or "None"

    # Work status counts
    work_by_status = pg.get("work_by_status") or {}
    work_status_rows = "".join(
        f"<tr>{td(k)}{td(v)}</tr>" for k, v in sorted(work_by_status.items())
    ) or "<tr><td colspan='2'>No data</td></tr>"

    # Latest WorkItems
    latest_work = pg.get("latest_work") or []
    work_rows = ""
    for w in latest_work:
        work_rows += (
            "<tr>"
            f"{td(w.get('created_at'))}"
            f"{td(w.get('updated_at'))}"
            f"{td(w.get('status'))}"
            f"{td(w.get('attempts'))}"
            f"{td(w.get('kind'))}"
            f"{td(w.get('business_id'))}"
            f"{td(w.get('client_id'))}"
            f"{td(w.get('ref_id'))}"
            f"{td(w.get('run_after'))}"
            f"{td(w.get('last_error'))}"
            f"{td(w.get('work_id'))}"
            "</tr>"
        )
    if not work_rows:
        work_rows = "<tr><td colspan='11'>No work items</td></tr>"

    # Latest InboundMessages (no status/attempts/etc)
    latest_inbound = pg.get("latest_inbound") or []
    inbound_rows = ""
    for m in latest_inbound:
        inbound_rows += (
            "<tr>"
            f"{td(m.get('created_at'))}"
            f"{td(m.get('updated_at'))}"
            f"{td(m.get('phone_number_id'))}"
            f"{td(m.get('from'))}"
            f"{td(m.get('message_id'))}"
            f"{td(m.get('timestamp'))}"
            f"{td(m.get('raw_preview'))}"
            f"{td(m.get('id'))}"
            "</tr>"
        )
    if not inbound_rows:
        inbound_rows = "<tr><td colspan='8'>No inbound messages</td></tr>"

    # Redis stream tail
    stream = (rd.get("stream") or {})
    stream_latest = stream.get("latest") or []
    stream_rows = ""
    for e in stream_latest:
        f = e.get("fields", {}) or {}
        meta = f.get("meta")
        meta_txt = _compact_json(meta, limit=280)
        stream_rows += (
            "<tr>"
            f"{td(f.get('ts'))}"
            f"{td(f.get('event'))}"
            f"{td(f.get('kind') or f.get('type'))}"
            f"{td(f.get('business_id'))}"
            f"{td(f.get('client_id'))}"
            f"{td(f.get('work_id') or f.get('inbound_id'))}"
            f"{td(f.get('attempt'))}"
            f"{td(meta_txt)}"
            "</tr>"
        )
    if not stream_rows:
        stream_rows = "<tr><td colspan='8'>No stream events</td></tr>"

    html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>tami debug</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui; margin: 24px; }}
    h2 {{ margin-top: 28px; }}
    .row {{ display: flex; gap: 24px; flex-wrap: wrap; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 14px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #eee; padding: 8px; font-size: 13px; vertical-align: top; }}
    th {{ background: #fafafa; text-align: left; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .small {{ font-size: 12px; color: #666; }}
  </style>
</head>
<body>
  <h1>tami debug</h1>

  <div class="row">
    <div class="card">
      <div><b>Redis queue</b> <span class="small">({escape(str(queue_name))})</span></div>
      <div class="mono" style="font-size:22px">{escape(str(queue_len))}</div>
    </div>
    <div class="card">
      <div><b>Redis errors</b></div>
      <div class="mono small">{redis_errs}</div>
    </div>
  </div>

  <h2>Postgres: WorkItem status counts</h2>
  <div class="card">
    <table>
      <thead><tr>{th("status")}{th("count")}</tr></thead>
      <tbody>{work_status_rows}</tbody>
    </table>
  </div>

  <h2>Postgres: Latest WorkItems</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          {th("created_at")}{th("updated_at")}{th("status")}{th("attempts")}
          {th("kind")}{th("business_id")}{th("client_id")}{th("ref_id")}
          {th("run_after")}{th("last_error")}{th("work_id")}
        </tr>
      </thead>
      <tbody>{work_rows}</tbody>
    </table>
  </div>

  <h2>Postgres: Latest InboundMessages</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          {th("created_at")}{th("updated_at")}
          {th("phone_number_id")}{th("from")}{th("message_id")}{th("timestamp")}
          {th("raw_preview")}{th("id")}
        </tr>
      </thead>
      <tbody>{inbound_rows}</tbody>
    </table>
  </div>

  <h2>Redis Stream: Latest events</h2>
  <div class="card">
    <table>
      <thead>
        <tr>
          {th("ts")}{th("event")}{th("kind/type")}{th("business_id")}
          {th("client_id")}{th("work_id/inbound_id")}{th("attempt")}{th("meta")}
        </tr>
      </thead>
      <tbody>{stream_rows}</tbody>
    </table>
  </div>

  <div class="small" style="margin-top:16px">
    Tip: refresh to update. Use <span class="mono">?count=50</span> to show more stream events.
  </div>
</body>
</html>
"""
    return HTMLResponse(html)
