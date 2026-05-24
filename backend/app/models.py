"""SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
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

    # IDs of research snippets that fed into this draft's prompt. Stored as a
    # JSON list rather than a join table so a single SELECT renders the draft +
    # its citations without an extra round-trip; (user_id, url) snippet
    # uniqueness already gives us stable IDs to reference here.
    cited_snippet_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

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
            "cited_snippet_ids": list(self.cited_snippet_ids or []),
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


class ResearchSubscription(Base):
    """A saved research configuration that runs autonomously on an interval.

    Turns the workbench from a manual tool into the actual compounding loop —
    set a subscription with a few queries / RSS feeds and an interval, and a
    cron-driven ``/research/tick`` endpoint will run them for you so banked
    snippets stay fresh without manual clicks.

    The tick endpoint (see ``store.due_subscriptions`` + ``main.research_tick``)
    uses ``last_run_at`` to skip subs that aren't due yet — so it's safe to
    poke every minute from a Vercel/Render cron without rate-burning Groq.
    """

    __tablename__ = "research_subscriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)

    name: Mapped[str] = mapped_column(String(128))
    queries: Mapped[list] = mapped_column(JSON, default=list)
    rss_feeds: Mapped[list] = mapped_column(JSON, default=list)
    sources: Mapped[list] = mapped_column(JSON, default=lambda: ["hn", "devto", "reddit", "rss"])

    # 1 = hourly, 24 = daily, 168 = weekly. Bounded server-side.
    interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_fetched_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        # ``due_subscriptions`` filters by (active, last_run_at) — keeping the
        # composite index hot lets cron polls stay sub-ms even at scale.
        Index("ix_research_subs_active_lastrun", "active", "last_run_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "queries": list(self.queries or []),
            "rss_feeds": list(self.rss_feeds or []),
            "sources": list(self.sources or []),
            "interval_hours": self.interval_hours,
            "active": self.active,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_fetched_count": self.last_fetched_count,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat(),
        }


class DraftOutcome(Base):
    """One observation of engagement on a posted draft.

    Append-only — every metric pull (likes after 1h, likes after 24h, etc.) is
    a new row.  Latest-per-kind is the natural read pattern.  The research
    loop joins back via ``Draft.cited_snippet_ids`` to find which sources fed
    drafts that performed well, then biases future top-snippet picks toward
    those sources.
    """

    __tablename__ = "draft_outcomes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    draft_id: Mapped[str] = mapped_column(String, index=True)

    platform: Mapped[str] = mapped_column(String(32))
    # likes | comments | views | reposts | clicks | shares | replies — open set
    # on purpose so new platforms can record what they have without a schema bump.
    metric_kind: Mapped[str] = mapped_column(String(32), index=True)
    metric_value: Mapped[int] = mapped_column(Integer, default=0)

    post_url: Mapped[str | None] = mapped_column(String, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_outcomes_user_seen", "user_id", "observed_at"),
        Index("ix_outcomes_user_kind", "user_id", "metric_kind", "observed_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "draft_id": self.draft_id,
            "platform": self.platform,
            "metric_kind": self.metric_kind,
            "metric_value": self.metric_value,
            "post_url": self.post_url,
            "observed_at": self.observed_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }


class OperatorRun(Base):
    """One autonomous cycle of the Eva operator.

    Picks an experiment (a subset of research snippets), drafts platform-
    tailored posts, and records the snippets + drafts it produced. Becomes
    the audit trail for "what did the operator try on 2026-05-24?" and the
    basis for comparing weighting strategies against each other later.
    """

    __tablename__ = "operator_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)

    product: Mapped[str] = mapped_column(Text)
    platforms: Mapped[list] = mapped_column(JSON, default=list)
    cited_snippet_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    draft_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    weight_by_leaderboard: Mapped[bool] = mapped_column(Boolean, default=True)
    leaderboard_metric: Mapped[str] = mapped_column(String(32), default="likes")

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_operator_runs_user_started", "user_id", "started_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "product": self.product,
            "platforms": list(self.platforms or []),
            "cited_snippet_ids": list(self.cited_snippet_ids or []),
            "draft_ids": list(self.draft_ids or []),
            "weight_by_leaderboard": self.weight_by_leaderboard,
            "leaderboard_metric": self.leaderboard_metric,
            "status": self.status,
            "error": self.error,
            "notes": self.notes,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class OperatorSubscription(Base):
    """A stored operator config that fires on a cadence.

    Tied to the `/operator/tick` endpoint (manual, per-user) and the
    `/operator/tick/all` service-auth fan-out endpoint that the hourly
    GitHub Action drives. ``last_run_at`` gates the cron so subs only fire
    when ``now - last_run_at >= interval_hours``.
    """

    __tablename__ = "operator_subscriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)

    name: Mapped[str] = mapped_column(String(128))
    product: Mapped[str] = mapped_column(Text)
    platforms: Mapped[list] = mapped_column(JSON, default=list)
    weight_by_leaderboard: Mapped[bool] = mapped_column(Boolean, default=True)
    leaderboard_metric: Mapped[str] = mapped_column(String(32), default="likes")
    snippet_limit: Mapped[int] = mapped_column(Integer, default=8)

    interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("ix_opsubs_active_lastrun", "active", "last_run_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "product": self.product,
            "platforms": list(self.platforms or []),
            "weight_by_leaderboard": self.weight_by_leaderboard,
            "leaderboard_metric": self.leaderboard_metric,
            "snippet_limit": self.snippet_limit,
            "interval_hours": self.interval_hours,
            "active": self.active,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_id": self.last_run_id,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat(),
        }
