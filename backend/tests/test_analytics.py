"""Tests for the engagement analytics rollup — per-channel + over-time views
built from the append-only draft_outcomes timeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main, store

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)  # a Thursday


def _make_draft(uid: str, platform: str = "x") -> str:
    fake_result = {
        "plan": {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
        "posts": {platform: {"draft": "raw", "feedback": "f", "final": "final"}},
    }
    return store.save_drafts(uid, "p" * 20, fake_result)[0]["id"]


def _obs(uid: str, draft_id: str, kind: str, value: int, days_ago: float) -> None:
    store.record_outcome(
        uid,
        draft_id,
        metric_kind=kind,
        metric_value=value,
        observed_at=NOW - timedelta(days=days_ago),
    )


# ---------------------------------------------------------------------------
# store-level
# ---------------------------------------------------------------------------


def test_empty_account_returns_zero_filled_series():
    out = store.engagement_analytics("u-empty", days=7, now=NOW)
    assert out["totals"] == {}
    assert out["channels"] == []
    assert out["draft_count"] == 0
    assert out["metric_kinds"] == []
    assert len(out["timeseries"]) == 7
    assert out["timeseries"][-1]["bucket_start"] == "2026-10-15"
    assert all(b["totals"] == {} for b in out["timeseries"])


def test_repeated_snapshots_count_as_gains_not_sums():
    """likes 10 → 25 → 40 is 40 likes earned, not 75."""
    uid = "u-gain"
    d = _make_draft(uid)
    _obs(uid, d, "likes", 10, days_ago=2)
    _obs(uid, d, "likes", 25, days_ago=1)
    _obs(uid, d, "likes", 40, days_ago=0)

    out = store.engagement_analytics(uid, days=7, now=NOW)
    assert out["totals"] == {"likes": 40}
    by_day = {b["bucket_start"]: b["totals"].get("likes", 0) for b in out["timeseries"]}
    assert by_day["2026-10-13"] == 10
    assert by_day["2026-10-14"] == 15
    assert by_day["2026-10-15"] == 15
    assert sum(by_day.values()) == out["totals"]["likes"]


def test_drop_in_scraped_value_never_subtracts():
    uid = "u-drop"
    d = _make_draft(uid)
    _obs(uid, d, "likes", 30, days_ago=2)
    _obs(uid, d, "likes", 20, days_ago=1)  # scrape glitch
    _obs(uid, d, "likes", 35, days_ago=0)

    out = store.engagement_analytics(uid, days=7, now=NOW)
    assert out["totals"]["likes"] == 35


def test_pre_window_observations_seed_baseline():
    """Only engagement earned inside the window counts."""
    uid = "u-base"
    d = _make_draft(uid)
    _obs(uid, d, "likes", 100, days_ago=20)
    _obs(uid, d, "likes", 130, days_ago=1)

    out = store.engagement_analytics(uid, days=7, now=NOW)
    assert out["totals"]["likes"] == 30
    all_time = store.engagement_analytics(uid, days=365, now=NOW)
    assert all_time["totals"]["likes"] == 130


def test_channels_ranked_by_engagement_excluding_views():
    uid = "u-chan"
    x1, x2 = _make_draft(uid, "x"), _make_draft(uid, "x")
    li = _make_draft(uid, "linkedin")
    _obs(uid, x1, "likes", 10, days_ago=1)
    _obs(uid, x2, "likes", 30, days_ago=1)
    _obs(uid, x2, "comments", 4, days_ago=1)
    _obs(uid, li, "likes", 5, days_ago=1)
    _obs(uid, li, "views", 10_000, days_ago=1)  # impressions shouldn't win the ranking

    out = store.engagement_analytics(uid, days=7, now=NOW)
    assert [c["platform"] for c in out["channels"]] == ["x", "linkedin"]
    x = out["channels"][0]
    assert x["draft_count"] == 2
    assert x["totals"] == {"likes": 40, "comments": 4}
    assert x["per_draft"] == {"likes": 20.0, "comments": 2.0}
    assert x["engagement"] == 44
    assert x["top_draft"]["draft_id"] == x2
    assert x["top_draft"]["metric_value"] == 30
    li_row = out["channels"][1]
    assert li_row["totals"]["views"] == 10_000
    assert li_row["engagement"] == 5
    # best post skips the 10k views in favour of a real interaction
    assert li_row["top_draft"]["metric_kind"] == "likes"
    assert out["totals"] == {"likes": 45, "comments": 4, "views": 10_000}
    assert out["metric_kinds"] == ["comments", "likes", "views"]
    assert out["draft_count"] == 3


def test_weekly_buckets_start_on_monday():
    uid = "u-week"
    d = _make_draft(uid)
    _obs(uid, d, "likes", 5, days_ago=10)  # Mon 2026-10-05
    _obs(uid, d, "likes", 12, days_ago=0)  # Thu 2026-10-15

    out = store.engagement_analytics(uid, days=14, bucket="week", now=NOW)
    starts = [b["bucket_start"] for b in out["timeseries"]]
    assert starts == ["2026-09-28", "2026-10-05", "2026-10-12"]
    assert [b["totals"].get("likes", 0) for b in out["timeseries"]] == [0, 5, 7]
    assert out["window"]["since"].startswith("2026-09-28")


def test_best_post_falls_back_to_views_when_nothing_else():
    uid = "u-views-only"
    d = _make_draft(uid, "instagram")
    _obs(uid, d, "views", 900, days_ago=1)
    ch = store.engagement_analytics(uid, days=7, now=NOW)["channels"][0]
    assert ch["top_draft"]["metric_kind"] == "views"
    assert ch["engagement"] == 0


def test_platform_filter():
    uid = "u-filter"
    x = _make_draft(uid, "x")
    bsky = _make_draft(uid, "bluesky")
    _obs(uid, x, "likes", 9, days_ago=1)
    _obs(uid, bsky, "likes", 3, days_ago=1)

    out = store.engagement_analytics(uid, days=7, platform="bluesky", now=NOW)
    assert out["totals"] == {"likes": 3}
    assert [c["platform"] for c in out["channels"]] == ["bluesky"]


def test_scoped_to_user():
    d = _make_draft("someone-else")
    _obs("someone-else", d, "likes", 50, days_ago=1)
    out = store.engagement_analytics("u-me", days=7, now=NOW)
    assert out["totals"] == {}


def test_future_observations_excluded():
    uid = "u-future"
    d = _make_draft(uid)
    _obs(uid, d, "likes", 7, days_ago=-2)
    assert store.engagement_analytics(uid, days=7, now=NOW)["totals"] == {}


@pytest.mark.parametrize("kwargs", [{"days": 0}, {"bucket": "month"}])
def test_rejects_bad_params(kwargs):
    with pytest.raises(ValueError):
        store.engagement_analytics("u", now=NOW, **kwargs)


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


def test_analytics_endpoint_aggregates_posted_outcomes():
    client = TestClient(main.app)
    uid = client.get("/me").json()["user_id"]
    d = _make_draft(uid, "mastodon")
    for v in (4, 9):
        client.post(f"/drafts/{d}/outcomes", json={"metric_kind": "likes", "metric_value": v})

    res = client.get("/analytics/engagement?days=7")
    assert res.status_code == 200
    body = res.json()
    assert body["window"]["days"] == 7
    assert body["window"]["bucket"] == "day"
    assert body["totals"] == {"likes": 9}
    assert body["channels"][0]["platform"] == "mastodon"
    assert len(body["timeseries"]) == 7


def test_analytics_endpoint_validates_params():
    client = TestClient(main.app)
    assert client.get("/analytics/engagement?days=0").status_code == 422
    assert client.get("/analytics/engagement?days=366").status_code == 422
    assert client.get("/analytics/engagement?bucket=month").status_code == 422
