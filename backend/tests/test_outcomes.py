"""Tests for the outcome-feedback collector — append-only engagement
observations on drafts and the source leaderboard that closes the loop."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main, store
from app.research import Snippet


# ---------------------------------------------------------------------------
# store-level
# ---------------------------------------------------------------------------


def _make_draft(uid: str, platform: str = "x", cited: list[str] | None = None) -> str:
    fake_result = {
        "plan": {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
        "posts": {platform: {"draft": "raw", "feedback": "f", "final": "final"}},
    }
    drafts = store.save_drafts(uid, "p" * 20, fake_result, cited_snippet_ids=cited or [])
    return drafts[0]["id"]


def test_record_outcome_appends_row():
    uid = "u-rec"
    draft_id = _make_draft(uid)

    row = store.record_outcome(uid, draft_id, metric_kind="likes", metric_value=12)
    assert row is not None
    assert row["draft_id"] == draft_id
    assert row["metric_kind"] == "likes"
    assert row["metric_value"] == 12
    assert row["platform"] == "x"
    assert row["observed_at"]  # ISO-formatted


def test_record_outcome_rejects_negative():
    uid = "u-neg"
    draft_id = _make_draft(uid)
    with pytest.raises(ValueError):
        store.record_outcome(uid, draft_id, metric_kind="likes", metric_value=-1)


def test_record_outcome_rejects_empty_kind():
    uid = "u-empty"
    draft_id = _make_draft(uid)
    with pytest.raises(ValueError):
        store.record_outcome(uid, draft_id, metric_kind="", metric_value=5)


def test_record_outcome_owners_only():
    """A draft belonging to user B is invisible to user A."""
    other_draft = _make_draft("user-other")
    row = store.record_outcome("user-A", other_draft, metric_kind="likes", metric_value=1)
    assert row is None


def test_record_outcome_inherits_draft_post_url():
    uid = "u-post-url"
    draft_id = _make_draft(uid)
    # Simulate the extension reporting the draft as posted.
    store.mark_posted(uid, draft_id, "https://x.com/u/status/123")

    row = store.record_outcome(uid, draft_id, metric_kind="likes", metric_value=3)
    assert row["post_url"] == "https://x.com/u/status/123"


def test_record_outcome_explicit_post_url_wins():
    uid = "u-explicit"
    draft_id = _make_draft(uid)
    store.mark_posted(uid, draft_id, "https://x.com/u/status/123")

    row = store.record_outcome(
        uid,
        draft_id,
        metric_kind="likes",
        metric_value=1,
        post_url="https://override.example/p/1",
    )
    assert row["post_url"] == "https://override.example/p/1"


def test_latest_outcomes_returns_most_recent_per_kind():
    uid = "u-latest"
    draft_id = _make_draft(uid)
    t0 = datetime(2026, 5, 1, tzinfo=timezone.utc)

    # Two likes samples (1h apart) + one comments sample.
    store.record_outcome(
        uid, draft_id, metric_kind="likes", metric_value=5, observed_at=t0
    )
    store.record_outcome(
        uid,
        draft_id,
        metric_kind="likes",
        metric_value=20,
        observed_at=t0 + timedelta(hours=1),
    )
    store.record_outcome(
        uid, draft_id, metric_kind="comments", metric_value=3, observed_at=t0
    )

    latest = store.latest_outcomes_for_draft(uid, draft_id)
    assert set(latest.keys()) == {"likes", "comments"}
    # Most-recent likes wins (20, not 5).
    assert latest["likes"]["metric_value"] == 20
    assert latest["comments"]["metric_value"] == 3


def test_outcomes_for_draft_returns_full_timeline():
    uid = "u-timeline"
    draft_id = _make_draft(uid)
    t0 = datetime(2026, 5, 1, tzinfo=timezone.utc)

    for i, v in enumerate([1, 4, 9]):
        store.record_outcome(
            uid,
            draft_id,
            metric_kind="likes",
            metric_value=v,
            observed_at=t0 + timedelta(hours=i),
        )

    timeline = store.outcomes_for_draft(uid, draft_id)
    assert [r["metric_value"] for r in timeline] == [1, 4, 9]


# ---------------------------------------------------------------------------
# leaderboard
# ---------------------------------------------------------------------------


def test_source_leaderboard_aggregates_by_source_query():
    """Two drafts cite snippets from different sources; the leaderboard sums
    the best-observed metric per draft into (source, query) buckets."""
    uid = "u-leader"

    # Bank snippets from two sources.
    saved = store.upsert_snippets(
        uid,
        [
            Snippet(source="hn", url="https://hn.example/a", title="A", score=0.9, query="agents"),
            Snippet(source="hn", url="https://hn.example/b", title="B", score=0.8, query="agents"),
            Snippet(source="reddit", url="https://rd.example/c", title="C", score=0.7, query="agents"),
        ],
    )
    ids_by_source: dict[str, list[str]] = {}
    for row in saved:
        ids_by_source.setdefault(row["source"], []).append(row["id"])

    # Two drafts: first cites both HN snippets, second cites the Reddit snippet.
    d1 = _make_draft(uid, cited=ids_by_source["hn"])
    d2 = _make_draft(uid, cited=ids_by_source["reddit"])

    # Sample two engagement points per draft so the "best wins" path runs.
    store.record_outcome(uid, d1, metric_kind="likes", metric_value=10)
    store.record_outcome(uid, d1, metric_kind="likes", metric_value=40)
    store.record_outcome(uid, d2, metric_kind="likes", metric_value=5)

    rows = store.source_leaderboard(uid, metric_kind="likes")
    by_source = {(r["source"], r["query"]): r for r in rows}

    # HN (agents) bucket: best of d1 = 40; counted once per cited snippet = 2 hits.
    hn_row = by_source[("hn", "agents")]
    assert hn_row["total"] == 80  # 40 × 2 cited HN snippets
    assert hn_row["draft_count"] == 2

    # Reddit bucket: best of d2 = 5, one snippet cited.
    rd_row = by_source[("reddit", "agents")]
    assert rd_row["total"] == 5
    assert rd_row["draft_count"] == 1

    # Sort order: HN row is first because total is larger.
    assert rows[0]["source"] == "hn"


def test_source_leaderboard_empty_when_no_outcomes():
    uid = "u-empty-leader"
    saved = store.upsert_snippets(
        uid,
        [Snippet(source="hn", url="https://hn.example/x", title="X", score=0.5, query="q")],
    )
    _make_draft(uid, cited=[saved[0]["id"]])
    assert store.source_leaderboard(uid, metric_kind="likes") == []


def test_source_leaderboard_respects_metric_kind():
    """A draft with 100 likes should not appear in the comments leaderboard."""
    uid = "u-metric-kind"
    saved = store.upsert_snippets(
        uid,
        [Snippet(source="hn", url="https://hn.example/k", title="K", score=0.5, query="q")],
    )
    d = _make_draft(uid, cited=[saved[0]["id"]])
    store.record_outcome(uid, d, metric_kind="likes", metric_value=100)
    assert store.source_leaderboard(uid, metric_kind="comments") == []


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


def test_post_outcome_endpoint_records_row():
    client = TestClient(main.app)
    uid = client.get("/me").json()["user_id"]
    draft_id = _make_draft(uid)

    res = client.post(
        f"/drafts/{draft_id}/outcomes",
        json={"metric_kind": "likes", "metric_value": 7},
    )
    assert res.status_code == 201
    assert res.json()["metric_value"] == 7


def test_post_outcome_endpoint_422_for_negative():
    client = TestClient(main.app)
    uid = client.get("/me").json()["user_id"]
    draft_id = _make_draft(uid)

    res = client.post(
        f"/drafts/{draft_id}/outcomes",
        json={"metric_kind": "likes", "metric_value": -1},
    )
    # FastAPI's Pydantic validation rejects ge=0 before our store helper runs.
    assert res.status_code == 422


def test_post_outcome_endpoint_404_for_unknown_draft():
    client = TestClient(main.app)
    res = client.post(
        "/drafts/does-not-exist/outcomes",
        json={"metric_kind": "likes", "metric_value": 1},
    )
    assert res.status_code == 404


def test_post_outcome_endpoint_owners_only():
    """Posting to another user's draft is a 404 (auth-leak parity)."""
    other_id = _make_draft("user-other")
    client = TestClient(main.app)
    res = client.post(
        f"/drafts/{other_id}/outcomes",
        json={"metric_kind": "likes", "metric_value": 1},
    )
    assert res.status_code == 404


def test_get_outcomes_endpoint_returns_latest_and_timeline():
    client = TestClient(main.app)
    uid = client.get("/me").json()["user_id"]
    draft_id = _make_draft(uid)

    for v in (3, 10):
        client.post(
            f"/drafts/{draft_id}/outcomes",
            json={"metric_kind": "likes", "metric_value": v},
        )

    res = client.get(f"/drafts/{draft_id}/outcomes")
    assert res.status_code == 200
    body = res.json()
    assert body["draft_id"] == draft_id
    assert body["latest"]["likes"]["metric_value"] == 10  # most recent
    assert len(body["timeline"]) == 2


def test_leaderboard_endpoint_returns_rows():
    client = TestClient(main.app)
    uid = client.get("/me").json()["user_id"]
    saved = store.upsert_snippets(
        uid,
        [Snippet(source="hn", url="https://hn.example/q", title="Q", score=0.5, query="q")],
    )
    d = _make_draft(uid, cited=[saved[0]["id"]])
    store.record_outcome(uid, d, metric_kind="likes", metric_value=11)

    res = client.get("/research/sources/leaderboard?metric=likes&limit=5")
    assert res.status_code == 200
    body = res.json()
    assert body["metric"] == "likes"
    assert body["rows"][0]["source"] == "hn"
    assert body["rows"][0]["total"] == 11


def test_leaderboard_endpoint_rejects_bad_limit():
    client = TestClient(main.app)
    res = client.get("/research/sources/leaderboard?limit=0")
    assert res.status_code == 422
    res = client.get("/research/sources/leaderboard?limit=999")
    assert res.status_code == 422
