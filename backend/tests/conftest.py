"""Pytest fixtures.

We force ``DATABASE_URL`` to in-memory sqlite **with a shared cache** so every
connection in a test process sees the same schema. Without ``cache=shared``
SQLAlchemy's pool gives each connection a fresh in-memory DB and the tables
are invisible to readers.
"""

from __future__ import annotations

import os

# Set BEFORE importing app modules — db.py reads DATABASE_URL at import time.
os.environ["DATABASE_URL"] = (
    "sqlite+pysqlite:///file:fanout_test?mode=memory&cache=shared&uri=true"
)
os.environ.setdefault("GROQ_API_KEY", "dummy-for-tests")

import pytest  # noqa: E402

from app import db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    """Drop + recreate the schema between tests so rows don't leak."""
    db.Base.metadata.drop_all(bind=db.engine)
    db.Base.metadata.create_all(bind=db.engine)
    yield
    db.Base.metadata.drop_all(bind=db.engine)
