import os
from dotenv import load_dotenv

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
