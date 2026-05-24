"""Tests for OperatorSubscription CRUD, due-subscription gating, and the
``/operator/tick`` + ``/operator/tick/all`` endpoints."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main, operator, store


def _stub_agent(monkeypatch, *, raise_exc: Exception | None = None):
    def fake_run(self, product, platforms, *, research_context=None):
        if raise_exc is not None:
            raise raise_exc
        return {
            "plan": {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
            "posts": {
                p: {"draft": "raw", "feedback": "f", "final": f"final-{p}"} for p in platforms
            },
        }

    monkeypatch.setattr(main.SocialAgent, "run", fake_run)


# ---------------------------------------------------------------------------
# store CRUD
# ---------------------------------------------------------------------------


def test_create_and_list_operator_subscription():
    uid = "u-sub"
    sub = store.create_operator_subscription(
        uid,
        name="daily",
        product="a sample product blurb",
        platforms=["x", "linkedin"],
    )
    assert sub["id"]
    assert sub["interval_hours"] == 24
    assert sub["active"] is True
    assert sub["last_run_at"] is None

    listed = store.list_operator_subscriptions(uid)
    assert [r["id"] for r in listed] == [sub["id"]]


def test_create_rejects_bad_interval():
    with pytest.raises(ValueError):
        store.create_operator_subscription(
            "u-bad",
            name="x",
            product="a sample product blurb",
            platforms=["x"],
            interval_hours=0,
        )


def test_update_operator_subscription_patches_fields():
    uid = "u-up"
    sub = store.create_operator_subscription(
        uid,
        name="orig",
        product="a sample product blurb",
        platforms=["x"],
    )
    out = store.update_operator_subscription(
        uid,
        sub["id"],
        name="renamed",
        platforms=["x", "linkedin"],
        active=False,
    )
    assert out["name"] == "renamed"
    assert out["platforms"] == ["x", "linkedin"]
    assert out["active"] is False


def test_update_operator_subscription_owners_only():
    other = store.create_operator_subscription(
        "user-other",
        name="x",
        product="a sample product blurb",
        platforms=["x"],
    )
    assert store.update_operator_subscription("user-A", other["id"], name="hijack") is None


def test_delete_operator_subscription():
    uid = "u-del"
    sub = store.create_operator_subscription(
        uid, name="x", product="a sample product blurb", platforms=["x"]
    )
    assert store.delete_operator_subscription(uid, sub["id"]) is True
    assert store.delete_operator_subscription(uid, sub["id"]) is False  # second delete = no-op


# ---------------------------------------------------------------------------
# due_operator_subscriptions
# ---------------------------------------------------------------------------


def test_due_subscriptions_includes_never_run():
    uid = "u-due"
    sub = store.create_operator_subscription(
        uid, name="x", product="a sample product blurb", platforms=["x"]
    )
    due = store.due_operator_subscriptions(user_id=uid)
    assert [r["id"] for r in due] == [sub["id"]]


def test_due_subscriptions_skips_recent_run():
    uid = "u-recent"
    sub = store.create_operator_subscription(
        uid,
        name="hourly",
        product="a sample product blurb",
        platforms=["x"],
        interval_hours=24,
    )
    # Ran 1 hour ago → not yet due for a 24h interval.
    store.mark_operator_subscription_run(
        sub["id"],
        run_id="run-x",
        when=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    due = store.due_operator_subscriptions(user_id=uid)
    assert due == []


def test_due_subscriptions_returns_when_overdue():
    uid = "u-overdue"
    sub = store.create_operator_subscription(
        uid,
        name="daily",
        product="a sample product blurb",
        platforms=["x"],
        interval_hours=24,
    )
    store.mark_operator_subscription_run(
        sub["id"],
        run_id="prev",
        when=datetime.now(timezone.utc) - timedelta(hours=25),
    )
    due = store.due_operator_subscriptions(user_id=uid)
    assert [r["id"] for r in due] == [sub["id"]]


def test_due_subscriptions_skips_inactive():
    uid = "u-off"
    store.create_operator_subscription(
        uid, name="x", product="a sample product blurb", platforms=["x"], active=False
    )
    assert store.due_operator_subscriptions(user_id=uid) == []


def test_due_subscriptions_all_users():
    """No user filter → walks every active sub regardless of owner."""
    store.create_operator_subscription("u-a", name="a", product="p" * 20, platforms=["x"])
    store.create_operator_subscription("u-b", name="b", product="p" * 20, platforms=["x"])
    all_due = store.due_operator_subscriptions()
    user_ids = sorted({r["user_id"] for r in all_due})
    assert user_ids == ["u-a", "u-b"]


# ---------------------------------------------------------------------------
# operator.tick_user / tick_all
# ---------------------------------------------------------------------------


def test_tick_user_fires_each_due_sub(monkeypatch):
    _stub_agent(monkeypatch)
    uid = "u-tick"
    store.create_operator_subscription(uid, name="one", product="p" * 20, platforms=["x"])
    store.create_operator_subscription(uid, name="two", product="p" * 20, platforms=["linkedin"])

    results = operator.tick_user(uid)
    assert {r["name"] for r in results} == {"one", "two"}
    assert all(r["error"] is None for r in results)
    # All subs now have a last_run_at, so they no longer count as due.
    assert store.due_operator_subscriptions(user_id=uid) == []


def test_tick_user_isolates_failures(monkeypatch):
    """A subscription that explodes mid-tick does not poison the rest of the
    batch."""
    uid = "u-mixed"
    store.create_operator_subscription(uid, name="good", product="p" * 20, platforms=["x"])
    bad = store.create_operator_subscription(
        uid, name="bad", product="p" * 20, platforms=["linkedin"]
    )

    # Patch: explode only when the "bad" subscription's platforms come through.
    real_run = main.SocialAgent.run

    def selective_run(self, product, platforms, *, research_context=None):
        if "linkedin" in platforms and len(platforms) == 1:
            raise RuntimeError("boom")
        return {
            "plan": {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
            "posts": {p: {"draft": "r", "feedback": "f", "final": "f"} for p in platforms},
        }

    monkeypatch.setattr(main.SocialAgent, "run", selective_run)

    results = operator.tick_user(uid)
    by_name = {r["name"]: r for r in results}
    assert by_name["good"]["error"] is None
    assert by_name["good"]["drafts"] == 1
    assert "RuntimeError" in (by_name["bad"]["error"] or "")
    # The bad sub recorded its error onto the subscription row.
    rows = {r["id"]: r for r in store.list_operator_subscriptions(uid)}
    assert "RuntimeError" in (rows[bad["id"]]["last_error"] or "")


def test_tick_all_walks_every_user(monkeypatch):
    _stub_agent(monkeypatch)
    store.create_operator_subscription("u-1", name="one", product="p" * 20, platforms=["x"])
    store.create_operator_subscription("u-2", name="two", product="p" * 20, platforms=["x"])

    results = operator.tick_all()
    assert len(results) == 2
    assert all(r["error"] is None for r in results)


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


def test_subscription_crud_endpoints(monkeypatch):
    _stub_agent(monkeypatch)
    client = TestClient(main.app)

    # Create
    res = client.post(
        "/operator/subscriptions",
        json={"name": "daily", "product": "p" * 20, "platforms": ["x"]},
    )
    assert res.status_code == 201
    sub = res.json()
    sub_id = sub["id"]

    # List
    res = client.get("/operator/subscriptions")
    assert [r["id"] for r in res.json()] == [sub_id]

    # Update
    res = client.patch(f"/operator/subscriptions/{sub_id}", json={"active": False})
    assert res.status_code == 200
    assert res.json()["active"] is False

    # Delete
    res = client.delete(f"/operator/subscriptions/{sub_id}")
    assert res.status_code == 200
    assert client.get("/operator/subscriptions").json() == []


def test_subscription_create_rejects_invalid_platform(monkeypatch):
    client = TestClient(main.app)
    res = client.post(
        "/operator/subscriptions",
        json={"name": "x", "product": "p" * 20, "platforms": ["nope"]},
    )
    assert res.status_code == 400


def test_subscription_update_404_for_unknown():
    client = TestClient(main.app)
    res = client.patch("/operator/subscriptions/does-not-exist", json={"active": False})
    assert res.status_code == 404


def test_tick_endpoint_runs_due_subs(monkeypatch):
    _stub_agent(monkeypatch)
    client = TestClient(main.app)
    client.post(
        "/operator/subscriptions",
        json={"name": "x", "product": "p" * 20, "platforms": ["x"]},
    )
    res = client.post("/operator/tick")
    assert res.status_code == 200
    ran = res.json()["ran"]
    assert len(ran) == 1
    assert ran[0]["error"] is None


def test_tick_all_403_when_secret_unset(monkeypatch):
    monkeypatch.delenv("OPERATOR_TICK_SECRET", raising=False)
    client = TestClient(main.app)
    res = client.post("/operator/tick/all", headers={"X-Tick-Secret": "anything"})
    assert res.status_code == 403


def test_tick_all_403_on_bad_secret(monkeypatch):
    monkeypatch.setenv("OPERATOR_TICK_SECRET", "expected")
    client = TestClient(main.app)
    res = client.post("/operator/tick/all", headers={"X-Tick-Secret": "wrong"})
    assert res.status_code == 403


def test_tick_all_runs_when_secret_matches(monkeypatch):
    monkeypatch.setenv("OPERATOR_TICK_SECRET", "right")
    _stub_agent(monkeypatch)
    # Set up a sub belonging to a different user so user-scoped tick wouldn't
    # see it but service tick does.
    store.create_operator_subscription(
        "user-other", name="x", product="p" * 20, platforms=["x"]
    )
    client = TestClient(main.app)
    res = client.post("/operator/tick/all", headers={"X-Tick-Secret": "right"})
    assert res.status_code == 200
    assert len(res.json()["ran"]) == 1
