"""Postgres-backed store. All operations are scoped to a user_id."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db import session_scope
from app.models import Draft, ResearchSnippet
from app.research import Snippet


CHANNEL_ADAPTERS = {
    "x": {"composer": "content-x.js", "supportsScheduling": True, "requiresApproval": False},
    "linkedin": {"composer": "content-linkedin.js", "supportsScheduling": True, "requiresApproval": True},
    "reddit": {"composer": "content-reddit.js", "supportsScheduling": False, "requiresApproval": True},
    "threads": {"composer": "content-threads.js", "supportsScheduling": False, "requiresApproval": True},
    "bluesky": {"composer": "content-bluesky.js", "supportsScheduling": True, "requiresApproval": False},
    "mastodon": {"composer": "content-mastodon.js", "supportsScheduling": True, "requiresApproval": False},
    "instagram": {"composer": "content-instagram.js", "supportsScheduling": False, "requiresApproval": True},
}


def channel_adapter_contract(platform: str) -> dict | None:
    adapter = CHANNEL_ADAPTERS.get(platform)
    if not adapter:
        return None
    return {"platform": platform, **adapter}


def build_review_checkpoint(draft: dict, confidence: float) -> dict:
    adapter = channel_adapter_contract(draft["platform"])
    approval_required = confidence < 0.7 or (adapter["requiresApproval"] if adapter else False)
    return {
        "draft_id": draft["id"],
        "platform": draft["platform"],
        "confidence": round(confidence, 3),
        "requires_review": approval_required,
        "recommended_action": "human_review" if approval_required else "queue",
    }


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


def set_review_checkpoint(user_id: str, draft_id: str, confidence: float, notes: str | None = None) -> dict | None:
    with session_scope() as s:
        d = s.get(Draft, draft_id)
        if not d or d.user_id != user_id:
            return None
        current_plan = d.plan or {}
        adapter = channel_adapter_contract(d.platform)
        current_plan["review"] = {
            "confidence": round(confidence, 3),
            "notes": notes,
            "requires_review": confidence < 0.7 or (adapter["requiresApproval"] if adapter else False),
        }
        d.plan = current_plan
        if current_plan["review"]["requires_review"]:
            d.status = "review_required"
        return d.to_dict()


def approve_review(user_id: str, draft_id: str, reviewer: str) -> dict | None:
    with session_scope() as s:
        d = s.get(Draft, draft_id)
        if not d or d.user_id != user_id:
            return None
        current_plan = d.plan or {}
        review = current_plan.get("review", {})
        review["approved_by"] = reviewer
        review["requires_review"] = False
        current_plan["review"] = review
        d.plan = current_plan
        d.status = "queued"
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


# ---------------------------------------------------------------------------
# Research snippets
# ---------------------------------------------------------------------------


def upsert_snippets(user_id: str, snippets: list[Snippet]) -> list[dict]:
    """Persist research snippets, deduping on (user_id, url).

    On conflict we *refresh* the row — score/title/snippet are updated to
    reflect the latest fetch, but ``used_in_draft_id`` is preserved so we
    don't lose the link back to a draft that already cited the URL.

    Implemented as ``select-then-insert-or-update`` so the same code path
    works on Postgres (production) and SQLite in-memory (CI smoke).
    """
    out: list[dict] = []
    with session_scope() as s:
        for snip in snippets:
            existing = s.scalar(
                select(ResearchSnippet)
                .where(ResearchSnippet.user_id == user_id)
                .where(ResearchSnippet.url == snip.url)
            )
            if existing is None:
                row = ResearchSnippet(
                    user_id=user_id,
                    source=snip.source,
                    query=snip.query,
                    url=snip.url,
                    title=snip.title,
                    snippet=snip.snippet,
                    author=snip.author,
                    score=snip.score,
                    published_at=snip.published_at,
                    extra=snip.extra or None,
                )
                s.add(row)
                s.flush()
                out.append(row.to_dict())
            else:
                # Refresh in place — keep ``used_in_draft_id`` and ``id`` stable.
                existing.score = snip.score
                existing.title = snip.title
                existing.snippet = snip.snippet or existing.snippet
                existing.author = snip.author or existing.author
                existing.published_at = snip.published_at or existing.published_at
                existing.extra = snip.extra or existing.extra
                s.flush()
                out.append(existing.to_dict())
    return out


def list_snippets(
    user_id: str,
    *,
    source: str | None = None,
    only_unused: bool = False,
    limit: int = 50,
) -> list[dict]:
    with session_scope() as s:
        stmt = select(ResearchSnippet).where(ResearchSnippet.user_id == user_id)
        if source:
            stmt = stmt.where(ResearchSnippet.source == source)
        if only_unused:
            stmt = stmt.where(ResearchSnippet.used_in_draft_id.is_(None))
        stmt = stmt.order_by(ResearchSnippet.score.desc(), ResearchSnippet.created_at.desc()).limit(limit)
        return [row.to_dict() for row in s.scalars(stmt)]


def top_snippets_for_agent(user_id: str, *, limit: int = 8) -> list[dict]:
    """Highest-scoring **unused** snippets — what the agent gets fed.

    ``unused`` keeps the loop compounding: every research run pulls in fresh
    items, the agent consumes them, and they fall out of the next prompt.
    """
    return list_snippets(user_id, only_unused=True, limit=limit)


def mark_snippets_used(user_id: str, snippet_ids: list[str], draft_id: str) -> int:
    if not snippet_ids:
        return 0
    count = 0
    with session_scope() as s:
        for sid in snippet_ids:
            row = s.get(ResearchSnippet, sid)
            if row is None or row.user_id != user_id:
                continue
            row.used_in_draft_id = draft_id
            count += 1
    return count
