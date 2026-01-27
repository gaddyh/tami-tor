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

OUTBOX_QUEUE_NAME = os.getenv("OUTBOX_QUEUE_NAME", "jobs:outbox")
OUTBOX_STALE_SECONDS = int(os.getenv("OUTBOX_STALE_SECONDS", "120"))  # 2 minutes
OUTBOX_SWEEP_BATCH = int(os.getenv("OUTBOX_SWEEP_BATCH", "500"))      # cap per run
OUTBOX_STREAM_KEY = os.getenv("OUTBOX_STREAM_KEY", "events:outbox")   # optional
OUTBOX_EMIT_STREAM = os.getenv("OUTBOX_EMIT_STREAM", "1") == "1"
