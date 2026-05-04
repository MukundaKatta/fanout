"""SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)  # Supabase auth.users.id (uuid as string)

    platform: Mapped[str] = mapped_column(String(32))
    product: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    post_url: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "platform": self.platform,
            "product": self.product,
            "content": self.content,
            "feedback": self.feedback,
            "plan": self.plan,
            "status": self.status,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "post_url": self.post_url,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }


# Composite index for the "due for posting" query.
Index("ix_drafts_user_status_sched", Draft.user_id, Draft.status, Draft.scheduled_at)


class ResearchSnippet(Base):
    """A unit of research a user has gathered.

    Sourced from free signal endpoints (HN Algolia, Dev.to, Reddit JSON, RSS).
    Used by the agent's planning step so drafts reference live conversations
    instead of just the static product description. Persisted so we can:
      * dedupe across runs (don't surface the same URL twice)
      * track which snippets fed into which draft (compounding learning)
      * power UI lists on the web side without re-fetching upstream
    """

    __tablename__ = "research_snippets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)

    # Where it came from — free-form so new sources don't need a schema bump.
    source: Mapped[str] = mapped_column(String(32), index=True)  # hn|devto|reddit|rss
    query: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)

    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 0..1 — combines upstream popularity (points/comments) with recency.
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # When this snippet was used by the agent for a draft, store the draft id.
    # NULL = not yet used (eligible to surface).
    used_in_draft_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # Raw payload from the upstream source for forensic / future re-scoring.
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        # Same URL ingested twice for the same user collapses to one row —
        # that's the dedup primitive the research loop relies on.
        UniqueConstraint("user_id", "url", name="uq_research_user_url"),
        Index("ix_research_user_score", "user_id", "score"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "source": self.source,
            "query": self.query,
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "author": self.author,
            "score": self.score,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "used_in_draft_id": self.used_in_draft_id,
            "created_at": self.created_at.isoformat(),
        }
