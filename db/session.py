# db/session.py
import os
from dotenv import load_dotenv

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Load .env for local dev. On Render, env vars exist already; this won't override them.
load_dotenv(".venv/.env")


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url



DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (set it in .env or Render env vars).")

DATABASE_URL = _normalize_database_url(DATABASE_URL)

# Sync engine (recommended for now)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db():
    """
    FastAPI dependency generator (optional for now).
    Usage later:
        def route(db=Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
