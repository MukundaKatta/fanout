"""Postgres-backed store. All operations are scoped to a user_id."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db import session_scope
from app.models import Draft


def save_drafts(user_id: str, product: str, result: dict) -> list[dict]:
    out = []
    with session_scope() as s:
        for platform, bundle in result["posts"].items():
            d = Draft(
                user_id=user_id,
                platform=platform,
                product=product,
                content=bundle["final"],
                feedback=bundle["feedback"],
                plan=result["plan"],
                status="pending",
            )
            s.add(d)
            s.flush()
            out.append(d.to_dict())
    return out


def save_variations(user_id: str, product: str, platform: str, variations: list[dict]) -> list[dict]:
    """Save N variation drafts (from agent.variations()) for a single platform."""
    out = []
    with session_scope() as s:
        for v in variations:
            d = Draft(
                user_id=user_id,
                platform=platform,
                product=product,
                content=v["content"],
                feedback=v.get("angle"),  # store the angle in 'feedback' for visibility
                plan=None,
                status="pending",
            )
            s.add(d)
            s.flush()
            out.append(d.to_dict())
    return out


def list_drafts(user_id: str, status: str | None = None) -> list[dict]:
    with session_scope() as s:
        stmt = select(Draft).where(Draft.user_id == user_id)
        if status:
            stmt = stmt.where(Draft.status == status)
        stmt = stmt.order_by(Draft.created_at.desc())
        return [d.to_dict() for d in s.scalars(stmt)]


def get_draft(user_id: str, draft_id: str) -> dict | None:
    with session_scope() as s:
        d = s.get(Draft, draft_id)
        if not d or d.user_id != user_id:
            return None
        return d.to_dict()


def update_content(user_id: str, draft_id: str, content: str) -> dict | None:
    with session_scope() as s:
        d = s.get(Draft, draft_id)
        if not d or d.user_id != user_id:
            return None
        d.content = content
        return d.to_dict()


def queue_now(user_id: str, draft_id: str) -> dict | None:
    with session_scope() as s:
        d = s.get(Draft, draft_id)
        if not d or d.user_id != user_id:
            return None
        d.status = "queued"
        d.scheduled_at = None
        return d.to_dict()


def schedule(user_id: str, draft_id: str, scheduled_at: datetime) -> dict | None:
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    with session_scope() as s:
        d = s.get(Draft, draft_id)
        if not d or d.user_id != user_id:
            return None
        d.status = "scheduled"
        d.scheduled_at = scheduled_at
        return d.to_dict()


def cancel_schedule(user_id: str, draft_id: str) -> dict | None:
    with session_scope() as s:
        d = s.get(Draft, draft_id)
        if not d or d.user_id != user_id:
            return None
        d.status = "pending"
        d.scheduled_at = None
        return d.to_dict()


def due_for_posting(user_id: str, platform: str | None = None) -> list[dict]:
    """Atomically claim due drafts (status=queued OR status=scheduled+past).

    Uses SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent polling.
    """
    now = datetime.now(timezone.utc)
    out = []
    with session_scope() as s:
        stmt = (
            select(Draft)
            .where(Draft.user_id == user_id)
            .where(
                (Draft.status == "queued")
                | ((Draft.status == "scheduled") & (Draft.scheduled_at <= now))
            )
            .with_for_update(skip_locked=True)
        )
        if platform:
            stmt = stmt.where(Draft.platform == platform)
        for d in s.scalars(stmt):
            d.status = "posting"
            out.append({"draft_id": d.id, "platform": d.platform, "content": d.content})
    return out


def mark_posted(user_id: str, draft_id: str, post_url: str | None) -> dict | None:
    with session_scope() as s:
        d = s.get(Draft, draft_id)
        if not d or d.user_id != user_id:
            return None
        d.status = "posted"
        d.post_url = post_url
        d.error = None
        return d.to_dict()


def mark_failed(user_id: str, draft_id: str, error: str) -> dict | None:
    with session_scope() as s:
        d = s.get(Draft, draft_id)
        if not d or d.user_id != user_id:
            return None
        d.status = "failed"
        d.error = error
        return d.to_dict()
