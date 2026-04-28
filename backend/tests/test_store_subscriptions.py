"""Tests for research-subscription store helpers (sqlite in-memory)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import store


def _create(user="user1", **kw):
    defaults = dict(
        name="My sub",
        queries=["ai agents"],
        rss_feeds=[],
        interval_hours=24,
        active=True,
    )
    defaults.update(kw)
    return store.create_subscription(user, **defaults)


def test_create_and_list():
    sub = _create()
    assert sub["queries"] == ["ai agents"]
    assert sub["interval_hours"] == 24
    assert sub["active"] is True
    assert sub["last_run_at"] is None

    rows = store.list_subscriptions("user1")
    assert len(rows) == 1
    assert rows[0]["id"] == sub["id"]


def test_create_rejects_empty_queries_and_feeds():
    with pytest.raises(ValueError):
        store.create_subscription("user1", name="x", queries=[], rss_feeds=[])


def test_create_rejects_bad_interval():
    with pytest.raises(ValueError):
        store.create_subscription(
            "user1", name="x", queries=["q"], rss_feeds=[], interval_hours=0
        )
    with pytest.raises(ValueError):
        store.create_subscription(
            "user1", name="x", queries=["q"], rss_feeds=[], interval_hours=24 * 7 + 1
        )


def test_update_partial_only_writes_passed_fields():
    sub = _create()
    patched = store.update_subscription("user1", sub["id"], active=False)
    assert patched is not None
    assert patched["active"] is False
    assert patched["name"] == "My sub"  # unchanged
    assert patched["queries"] == ["ai agents"]


def test_update_rejects_clearing_both_lists():
    sub = _create()
    with pytest.raises(ValueError):
        store.update_subscription("user1", sub["id"], queries=[], rss_feeds=[])


def test_update_404_for_other_users_row():
    sub = _create(user="user1")
    assert store.update_subscription("user2", sub["id"], active=False) is None


def test_delete_owners_only():
    sub = _create(user="user1")
    assert store.delete_subscription("user2", sub["id"]) is False
    assert store.delete_subscription("user1", sub["id"]) is True
    assert store.list_subscriptions("user1") == []


def test_due_includes_never_run():
    sub = _create()
    due = store.due_subscriptions(user_id="user1")
    assert [d["id"] for d in due] == [sub["id"]]


def test_due_skips_recently_run():
    sub = _create(interval_hours=24)
    # Mark as just run.
    store.mark_subscription_run(sub["id"], fetched=3)
    due = store.due_subscriptions(user_id="user1")
    assert due == []


def test_due_re_includes_after_interval_elapses():
    sub = _create(interval_hours=1)
    # Pretend it ran 2 hours ago.
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    store.mark_subscription_run(sub["id"], fetched=0, when=past)
    due = store.due_subscriptions(user_id="user1")
    assert [d["id"] for d in due] == [sub["id"]]


def test_due_skips_inactive():
    sub = _create(active=False)
    assert store.due_subscriptions(user_id="user1") == []
    # Re-activate and it shows up:
    store.update_subscription("user1", sub["id"], active=True)
    assert len(store.due_subscriptions(user_id="user1")) == 1


def test_due_filters_by_user():
    a = _create(user="user1")
    b = _create(user="user2")
    user1_due = store.due_subscriptions(user_id="user1")
    user2_due = store.due_subscriptions(user_id="user2")
    assert [d["id"] for d in user1_due] == [a["id"]]
    assert [d["id"] for d in user2_due] == [b["id"]]


def test_due_global_returns_all_users_when_no_filter():
    a = _create(user="user1")
    b = _create(user="user2")
    all_due = store.due_subscriptions()
    ids = sorted(d["id"] for d in all_due)
    assert ids == sorted([a["id"], b["id"]])


def test_mark_run_records_error():
    sub = _create()
    out = store.mark_subscription_run(sub["id"], fetched=0, error="boom")
    assert out is not None
    assert out["last_error"] == "boom"
    assert out["last_fetched_count"] == 0
    assert out["last_run_at"] is not None
