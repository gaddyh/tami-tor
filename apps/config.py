import os
from dotenv import load_dotenv
from fastapi import Request, Depends
from temporalio.client import Client
from adapters.cloud_api import CloudAPIAdapter
from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv(".venv/.env")


def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None or v == "":
        raise RuntimeError(f"Missing required env var: {name}")
    return v


DATABASE_URL = env("DATABASE_URL")
REDIS_URL = env("REDIS_URL")

# ----------------------------
# WorkItem architecture defaults
# ----------------------------
# LIST queue (RPUSH/BLPOP/LLEN)
WORK_QUEUE_NAME = os.getenv("WORK_QUEUE_NAME", "jobs:work")
WORK_STALE_SECONDS = int(os.getenv("WORK_STALE_SECONDS", "120"))
WORK_SWEEP_BATCH = int(os.getenv("WORK_SWEEP_BATCH", "500"))

# STREAM for observability (XADD/XREVRANGE)
WORK_STREAM_KEY = os.getenv("WORK_STREAM_KEY", "events:work")
WORK_EMIT_STREAM = os.getenv("WORK_EMIT_STREAM", "1") == "1"

def _assert_no_stream_key_used_for_queue(var_name: str, value: str) -> None:
    if value.startswith("events:"):
        raise RuntimeError(
            f"{var_name} is set to '{value}', which looks like a STREAM key. "
            "Queue names must be LIST keys like 'jobs:work' (not 'events:*')."
        )


# Guardrails to prevent the exact WRONGTYPE bug from ever happening again
_assert_no_stream_key_used_for_queue("WORK_QUEUE_NAME", WORK_QUEUE_NAME)


def get_temporal_client(request: Request) -> Client:
    return request.app.state.temporal_client


def get_adapter(request: Request) -> CloudAPIAdapter:
    return request.app.state.adapter

tami_wa_id = "723503380842690"
tami_tor_wa_id = "816205444920021"
tami_tor_alin_wa_id = "982974261547358"

def get_adapter_global() -> CloudAPIAdapter:
    adapter = CloudAPIAdapter(phone_number_id=tami_tor_wa_id)
    return adapter

def get_timezone() -> ZoneInfo:
    return ZoneInfo("Asia/Jerusalem")

def get_timezone_str() -> str:
    return "Asia/Jerusalem"
    
def now_israel():
    tz = get_timezone()
    return datetime.now(tz)