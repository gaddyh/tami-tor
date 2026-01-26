# db/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base for all SQLAlchemy ORM models."""
    pass
