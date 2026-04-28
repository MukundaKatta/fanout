"""End-to-end test for the /research/tick flow using FastAPI's TestClient.

We mock ``run_research`` so the test never touches the network — it just
verifies the orchestration: due subs run, recently-run subs are skipped,
and the response shape matches the contract the UI consumes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import main, store
from app.research import Snippet


def _client(monkeypatch):
    """Build a TestClient with auth + research mocked.

    ``current_user`` defaults to dev mode in app.auth, so a fresh session
    sees a stable test user — no header juggling needed.
    """
    fake_snippets = [
        Snippet(source="hn", url=f"https://e.com/{i}", title=f"t{i}", score=0.5)
        for i in range(3)
    ]
    monkeypatch.setattr(main, "run_research", lambda req: list(fake_snippets))
    return TestClient(main.app)


def _uid(client: TestClient) -> str:
    return client.get("/me").json()["user_id"]


def test_tick_runs_due_subscriptions(monkeypatch):
    client = _client(monkeypatch)
    uid = _uid(client)

    # Two subs — one due, one already-run-recently.
    fresh = store.create_subscription(
        uid, name="fresh", queries=["agents"], rss_feeds=[], interval_hours=1
    )
    recent = store.create_subscription(
        uid, name="recent", queries=["other"], rss_feeds=[], interval_hours=24
    )
    store.mark_subscription_run(recent["id"], fetched=5)  # marks last_run_at = now

    res = client.post("/research/tick")
    assert res.status_code == 200
    body = res.json()
    ran_ids = sorted(r["id"] for r in body["ran"])
    assert ran_ids == [fresh["id"]]  # only the fresh one

    # The fresh sub now has last_run_at populated.
    after = store.list_subscriptions(uid)
    by_id = {s["id"]: s for s in after}
    assert by_id[fresh["id"]]["last_run_at"] is not None
    assert by_id[fresh["id"]]["last_fetched_count"] == 3
    assert by_id[fresh["id"]]["last_error"] is None


def test_tick_records_run_error(monkeypatch):
    client = TestClient(main.app)
    uid = _uid(client)
    store.create_subscription(
        uid, name="busted", queries=["x"], rss_feeds=[], interval_hours=1
    )

    def boom(_req):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(main, "run_research", boom)

    res = client.post("/research/tick")
    assert res.status_code == 200
    ran = res.json()["ran"]
    assert len(ran) == 1
    assert ran[0]["fetched"] == 0
    assert ran[0]["error"] == "upstream down"


def test_subscription_crud_endpoints(monkeypatch):
    client = TestClient(main.app)
    uid = _uid(client)

    # Create
    res = client.post(
        "/research/subscriptions",
        json={"name": "Sub A", "queries": ["a"], "interval_hours": 6},
    )
    assert res.status_code == 201
    sub = res.json()
    assert sub["queries"] == ["a"]

    # List
    res = client.get("/research/subscriptions")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # Patch
    res = client.patch(f"/research/subscriptions/{sub['id']}", json={"active": False})
    assert res.status_code == 200
    assert res.json()["active"] is False

    # Reject patch that empties both lists
    res = client.patch(
        f"/research/subscriptions/{sub['id']}",
        json={"queries": [], "rss_feeds": []},
    )
    assert res.status_code == 400

    # Delete
    res = client.delete(f"/research/subscriptions/{sub['id']}")
    assert res.status_code == 200
    assert client.get("/research/subscriptions").json() == []

    # 404 after delete
    res = client.delete(f"/research/subscriptions/{sub['id']}")
    assert res.status_code == 404


def test_subscription_create_rejects_empty():
    client = TestClient(main.app)
    res = client.post("/research/subscriptions", json={"name": "x"})
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# /research/tick/all — service-auth fan-out for cron
# ---------------------------------------------------------------------------


def test_tick_all_403_when_secret_unset(monkeypatch):
    monkeypatch.delenv("RESEARCH_TICK_SECRET", raising=False)
    client = TestClient(main.app)
    res = client.post("/research/tick/all", headers={"X-Tick-Secret": "anything"})
    assert res.status_code == 403
    assert "disabled" in res.json()["detail"].lower()


def test_tick_all_403_on_wrong_secret(monkeypatch):
    monkeypatch.setenv("RESEARCH_TICK_SECRET", "the-right-one")
    client = TestClient(main.app)
    res = client.post("/research/tick/all", headers={"X-Tick-Secret": "wrong"})
    assert res.status_code == 403


def test_tick_all_403_when_header_missing(monkeypatch):
    monkeypatch.setenv("RESEARCH_TICK_SECRET", "the-right-one")
    client = TestClient(main.app)
    res = client.post("/research/tick/all")
    assert res.status_code == 403


def test_tick_all_runs_across_users(monkeypatch):
    monkeypatch.setenv("RESEARCH_TICK_SECRET", "service-cron-token")
    client = _client(monkeypatch)

    # Two subs, two distinct users — both due (never run).
    sub_a = store.create_subscription(
        "user-alpha", name="alpha", queries=["q"], rss_feeds=[], interval_hours=1
    )
    sub_b = store.create_subscription(
        "user-beta", name="beta", queries=["q"], rss_feeds=[], interval_hours=1
    )

    res = client.post(
        "/research/tick/all", headers={"X-Tick-Secret": "service-cron-token"}
    )
    assert res.status_code == 200
    body = res.json()
    user_ids = sorted(r["user_id"] for r in body["ran"])
    assert user_ids == sorted(["user-alpha", "user-beta"])

    ran_ids = sorted(r["id"] for r in body["ran"])
    assert ran_ids == sorted([sub_a["id"], sub_b["id"]])
