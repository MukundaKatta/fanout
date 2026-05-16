"""Tests for research-snippet store helpers (sqlite in-memory)."""

from __future__ import annotations

from datetime import datetime, timezone

from app import store
from app.research import Snippet


def _snip(url: str, *, score: float = 0.5, title: str = "t") -> Snippet:
    return Snippet(
        source="hn",
        url=url,
        title=title,
        snippet="s",
        author="a",
        score=score,
        published_at=datetime.now(timezone.utc),
        query="q",
        extra={"k": "v"},
    )


def test_upsert_inserts_new_rows():
    saved = store.upsert_snippets("user1", [_snip("https://a"), _snip("https://b")])
    assert {row["url"] for row in saved} == {"https://a", "https://b"}
    assert all(row["used_in_draft_id"] is None for row in saved)


def test_upsert_dedupes_per_user_per_url():
    # First ingest
    first = store.upsert_snippets("user1", [_snip("https://a", score=0.3, title="old")])
    first_id = first[0]["id"]
    # Second ingest with same URL → row updated, id preserved
    second = store.upsert_snippets("user1", [_snip("https://a", score=0.9, title="new")])
    assert second[0]["id"] == first_id
    assert second[0]["score"] == 0.9
    assert second[0]["title"] == "new"

    # Different user, same URL → independent row
    other = store.upsert_snippets("user2", [_snip("https://a", score=0.5)])
    assert other[0]["id"] != first_id


def test_top_snippets_for_agent_only_unused_and_score_ordered():
    rows = store.upsert_snippets(
        "user1",
        [
            _snip("https://a", score=0.9),
            _snip("https://b", score=0.5),
            _snip("https://c", score=0.1),
        ],
    )
    # Mark the highest-scoring snippet as used.
    used_id = next(r["id"] for r in rows if r["url"] == "https://a")
    store.mark_snippets_used("user1", [used_id], draft_id="draft-xyz")

    top = store.top_snippets_for_agent("user1", limit=10)
    assert [r["url"] for r in top] == ["https://b", "https://c"]


def test_mark_snippets_used_only_affects_owners_rows():
    rows1 = store.upsert_snippets("user1", [_snip("https://a")])
    rows2 = store.upsert_snippets("user2", [_snip("https://a")])
    # user1 tries to mark user2's snippet — must be ignored.
    n = store.mark_snippets_used("user1", [rows2[0]["id"]], draft_id="dx")
    assert n == 0
    # And user1's own snippet flips correctly:
    n = store.mark_snippets_used("user1", [rows1[0]["id"]], draft_id="dx")
    assert n == 1
    assert store.list_snippets("user1", only_unused=True) == []


def test_list_snippets_filters():
    store.upsert_snippets(
        "user1",
        [
            Snippet(source="hn", url="https://a", title="t", score=0.3),
            Snippet(source="reddit", url="https://b", title="t", score=0.5),
        ],
    )
    hn = store.list_snippets("user1", source="hn")
    assert [r["url"] for r in hn] == ["https://a"]
    reddit = store.list_snippets("user1", source="reddit")
    assert [r["url"] for r in reddit] == ["https://b"]
