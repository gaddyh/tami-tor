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

INBOUND_QUEUE_NAME = os.getenv("INBOUND_QUEUE_NAME", "jobs:inbound")
INBOUND_STALE_SECONDS = int(os.getenv("INBOUND_STALE_SECONDS", "120"))  # 2 minutes
INBOUND_SWEEP_BATCH = int(os.getenv("INBOUND_SWEEP_BATCH", "500"))      # cap per run
INBOUND_STREAM_KEY = os.getenv("INBOUND_STREAM_KEY", "events:inbound")   # optional
INBOUND_EMIT_STREAM = os.getenv("INBOUND_EMIT_STREAM", "1") == "1"
