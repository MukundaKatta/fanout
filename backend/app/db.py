"""SQLAlchemy engine, session, and table init."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import SingletonThreadPool

from app.models import Base

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/fanout"
)


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"pool_pre_ping": True}
    # SQLAlchemy 2.1 deprecated picking SingletonThreadPool implicitly for
    # ``mode=memory`` sqlite URLs (tests / CI); a future release switches to
    # QueuePool. State the current pool explicitly so behaviour doesn't change
    # under a dependency bump.
    if url.startswith("sqlite") and "mode=memory" in url:
        kwargs["poolclass"] = SingletonThreadPool
    return kwargs


# echo=False; flip on for SQL debugging.
engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create tables if they don't exist. Use Alembic for real migrations."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
