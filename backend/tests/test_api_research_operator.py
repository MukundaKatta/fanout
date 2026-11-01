"""Route tests for /research (run, list, suggest, subscriptions, service tick)
and /operator (run, runs, subscriptions, service tick).

Network (HN / Reddit / Dev.to / RSS) is stubbed at ``main.run_research``;
Groq is stubbed by monkeypatching ``SocialAgent`` methods.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main, store
from app.research import Snippet

PRODUCT = "A product blurb long enough to validate"
PLAN = {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main.SocialAgent, "__init__", lambda self, *a, **k: None)

    def fake_run(self, product, platforms, *, research_context=None):
        return {
            "plan": PLAN,
            "posts": {p: {"draft": "raw", "feedback": "LGTM", "final": f"final-{p}"} for p in platforms},
        }

    monkeypatch.setattr(main.SocialAgent, "run", fake_run)
    calls: list = []

    def fake_research(req):
        calls.append(req)
        return [
            Snippet(source="hn", url="https://e.com/1", title="one", score=0.9),
            Snippet(source="reddit", url="https://e.com/2", title="two", score=0.4),
        ]

    monkeypatch.setattr(main, "run_research", fake_research)
    c = TestClient(main.app)
    c.research_calls = calls
    return c


def _uid(client):
    return client.get("/me").json()["user_id"]


# --- /research ---------------------------------------------------------------


def test_research_run_requires_query_or_feed(client):
    res = client.post("/research", json={})
    assert res.status_code == 400
    assert client.research_calls == []


def test_research_run_banks_snippets_and_forwards_params(client):
    res = client.post(
        "/research",
        json={"queries": ["agents"], "rss_feeds": ["https://f.example/rss"], "sources": ["hn"], "per_source_limit": 3},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["fetched"] == 2
    assert [r["title"] for r in body["saved"]] == ["one", "two"]
    req = client.research_calls[0]
    assert req.queries == ["agents"]
    assert req.rss_feeds == ["https://f.example/rss"]
    assert req.sources == ["hn"]
    assert req.per_source_limit == 3


def test_research_run_is_idempotent_on_url(client):
    client.post("/research", json={"queries": ["agents"]})
    second = client.post("/research", json={"queries": ["agents"]}).json()
    assert second["fetched"] == 2
    assert len(client.get("/research").json()) == 2


def test_research_run_validates_limits(client):
    assert client.post("/research", json={"queries": ["q"], "per_source_limit": 0}).status_code == 422
    assert client.post("/research", json={"queries": ["q"], "per_source_limit": 26}).status_code == 422
    assert client.post("/research", json={"queries": [f"q{i}" for i in range(11)]}).status_code == 422


def test_research_list_filters(client):
    client.post("/research", json={"queries": ["agents"]})
    all_rows = client.get("/research").json()
    assert [r["title"] for r in all_rows] == ["one", "two"]  # score desc
    assert [r["title"] for r in client.get("/research", params={"source": "reddit"}).json()] == ["two"]
    assert len(client.get("/research", params={"limit": 1}).json()) == 1
    store.mark_snippets_used(_uid(client), [all_rows[0]["id"]], "draft-x")
    unused = client.get("/research", params={"only_unused": True}).json()
    assert [r["title"] for r in unused] == ["two"]


def test_research_suggest(client, monkeypatch):
    seen = {}

    def fake_suggest(self, product, *, n=5):
        seen["n"] = n
        return ["q1", "q2"]

    monkeypatch.setattr(main.SocialAgent, "suggest_research_queries", fake_suggest)
    res = client.post("/research/suggest", json={"product": PRODUCT, "count": 2})
    assert res.json() == {"queries": ["q1", "q2"]}
    assert seen["n"] == 2
    assert client.post("/research/suggest", json={"product": PRODUCT, "count": 11}).status_code == 422


# --- research subscriptions --------------------------------------------------


def test_subscription_crud(client):
    res = client.post("/research/subscriptions", json={"name": "ai", "queries": ["agents"], "interval_hours": 6})
    assert res.status_code == 201
    sub = res.json()
    assert sub["name"] == "ai" and sub["interval_hours"] == 6 and sub["active"] is True

    assert [s["id"] for s in client.get("/research/subscriptions").json()] == [sub["id"]]

    patched = client.patch(
        f"/research/subscriptions/{sub['id']}",
        json={"name": "renamed", "active": False, "rss_feeds": ["https://f/rss"], "sources": ["rss"]},
    ).json()
    assert patched["name"] == "renamed"
    assert patched["active"] is False
    assert patched["rss_feeds"] == ["https://f/rss"]
    assert patched["sources"] == ["rss"]
    assert patched["queries"] == ["agents"]  # untouched

    assert client.delete(f"/research/subscriptions/{sub['id']}").json() == {"deleted": sub["id"]}
    assert client.get("/research/subscriptions").json() == []
    assert client.delete(f"/research/subscriptions/{sub['id']}").status_code == 404


def test_subscription_create_validation(client):
    assert client.post("/research/subscriptions", json={"name": "x"}).status_code == 400
    assert client.post("/research/subscriptions", json={"name": "", "queries": ["q"]}).status_code == 422
    assert (
        client.post("/research/subscriptions", json={"name": "x", "queries": ["q"], "interval_hours": 0}).status_code
        == 422
    )


def test_subscription_create_store_value_error_maps_to_400(client, monkeypatch):
    def boom(*a, **k):
        raise ValueError("nope")

    monkeypatch.setattr(main.store, "create_subscription", boom)
    res = client.post("/research/subscriptions", json={"name": "x", "queries": ["q"]})
    assert res.status_code == 400 and res.json()["detail"] == "nope"


def test_subscription_update_404_and_validation(client, monkeypatch):
    assert client.patch("/research/subscriptions/nope", json={"name": "x"}).status_code == 404
    other = store.create_subscription("other-user", name="o", queries=["q"], rss_feeds=[])
    assert client.patch(f"/research/subscriptions/{other['id']}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/research/subscriptions/{other['id']}").status_code == 404
    sub = client.post("/research/subscriptions", json={"name": "x", "queries": ["q"]}).json()
    assert client.patch(f"/research/subscriptions/{sub['id']}", json={"interval_hours": 999}).status_code == 422

    def boom(*a, **k):
        raise ValueError("bad update")

    monkeypatch.setattr(main.store, "update_subscription", boom)
    res = client.patch(f"/research/subscriptions/{sub['id']}", json={"name": "y"})
    assert res.status_code == 400 and res.json()["detail"] == "bad update"


def test_tick_records_error_when_research_raises(client, monkeypatch):
    def boom(req):
        raise RuntimeError("upstream exploded")

    monkeypatch.setattr(main, "run_research", boom)
    sub = client.post("/research/subscriptions", json={"name": "x", "queries": ["q"]}).json()
    body = client.post("/research/tick").json()
    assert body["ran"][0]["fetched"] == 0
    assert "upstream exploded" in body["ran"][0]["error"]
    stored = client.get("/research/subscriptions").json()[0]
    assert stored["id"] == sub["id"]
    assert "upstream exploded" in stored["last_error"]


# --- /research/tick/all (service auth) ---------------------------------------


def test_research_tick_all_disabled_without_secret(client, monkeypatch):
    monkeypatch.delenv("RESEARCH_TICK_SECRET", raising=False)
    res = client.post("/research/tick/all", headers={"X-Tick-Secret": "anything"})
    assert res.status_code == 403
    assert "disabled" in res.json()["detail"]


@pytest.mark.parametrize("headers", [{}, {"X-Tick-Secret": "wrong"}])
def test_research_tick_all_rejects_bad_secret(client, monkeypatch, headers):
    monkeypatch.setenv("RESEARCH_TICK_SECRET", "s3cret")
    assert client.post("/research/tick/all", headers=headers).status_code == 403


def test_research_tick_all_runs_every_users_due_subs(client, monkeypatch):
    monkeypatch.setenv("RESEARCH_TICK_SECRET", "s3cret")
    a = store.create_subscription("alice", name="a", queries=["q"], rss_feeds=[])
    b = store.create_subscription("bob", name="b", queries=[], rss_feeds=["https://f/rss"])
    store.create_subscription("carol", name="c", queries=["q"], rss_feeds=[], active=False)
    res = client.post("/research/tick/all", headers={"X-Tick-Secret": "s3cret"})
    assert res.status_code == 200
    ran = {r["id"]: r for r in res.json()["ran"]}
    assert set(ran) == {a["id"], b["id"]}
    assert ran[a["id"]]["user_id"] == "alice"
    assert ran[b["id"]]["fetched"] == 2
    # Snippets landed under each owner.
    assert len(store.list_snippets("alice")) == 2
    assert len(store.list_snippets("bob")) == 2
    # Second tick: nothing due.
    assert client.post("/research/tick/all", headers={"X-Tick-Secret": "s3cret"}).json()["ran"] == []


# --- /operator ---------------------------------------------------------------


def test_operator_run_invalid_platform_is_400(client):
    res = client.post("/operator/run", json={"product": PRODUCT, "platforms": ["myspace"]})
    assert res.status_code == 400


def test_operator_run_and_audit_trail(client):
    uid = _uid(client)
    store.upsert_snippets(uid, [Snippet(source="hn", url="https://e.com/z", title="z", score=0.8)])
    res = client.post("/operator/run", json={"product": PRODUCT, "platforms": ["x", "bluesky"]})
    assert res.status_code == 200
    body = res.json()
    assert body["plan"] == PLAN
    assert {d["platform"] for d in body["drafts"]} == {"x", "bluesky"}
    assert len(body["picked_snippets"]) == 1
    assert body["leaderboard_used"] is False

    runs = client.get("/operator/runs").json()
    assert [r["id"] for r in runs] == [body["operator_run_id"]]
    one = client.get(f"/operator/runs/{body['operator_run_id']}").json()
    assert one["status"] == "ok"
    assert client.get("/operator/runs/nope").status_code == 404


@pytest.mark.parametrize("limit", [0, 101])
def test_operator_runs_limit_bounds(client, limit):
    assert client.get("/operator/runs", params={"limit": limit}).status_code == 422


def test_operator_subscription_crud(client):
    res = client.post(
        "/operator/subscriptions",
        json={"name": "daily", "product": PRODUCT, "platforms": ["x"], "interval_hours": 12},
    )
    assert res.status_code == 201
    sub = res.json()
    assert sub["platforms"] == ["x"] and sub["interval_hours"] == 12

    assert [s["id"] for s in client.get("/operator/subscriptions").json()] == [sub["id"]]

    patched = client.patch(
        f"/operator/subscriptions/{sub['id']}",
        json={"platforms": ["x", "linkedin"], "active": False, "snippet_limit": 3, "leaderboard_metric": "views"},
    ).json()
    assert patched["platforms"] == ["x", "linkedin"]
    assert patched["active"] is False
    assert patched["snippet_limit"] == 3
    assert patched["leaderboard_metric"] == "views"

    assert client.delete(f"/operator/subscriptions/{sub['id']}").json() == {"deleted": sub["id"]}
    assert client.delete(f"/operator/subscriptions/{sub['id']}").status_code == 404


def test_operator_subscription_validation(client, monkeypatch):
    bad = client.post("/operator/subscriptions", json={"name": "n", "product": PRODUCT, "platforms": ["myspace"]})
    assert bad.status_code == 400
    sub = client.post("/operator/subscriptions", json={"name": "n", "product": PRODUCT}).json()
    assert client.patch(f"/operator/subscriptions/{sub['id']}", json={"platforms": ["nope"]}).status_code == 400
    assert client.patch("/operator/subscriptions/nope", json={"name": "x"}).status_code == 404

    def boom(*a, **k):
        raise ValueError("bad")

    monkeypatch.setattr(main.store, "create_operator_subscription", boom)
    monkeypatch.setattr(main.store, "update_operator_subscription", boom)
    assert client.post("/operator/subscriptions", json={"name": "n", "product": PRODUCT}).status_code == 422
    assert client.patch(f"/operator/subscriptions/{sub['id']}", json={"name": "y"}).status_code == 422


def test_operator_tick_runs_due_subs(client):
    client.post("/operator/subscriptions", json={"name": "n", "product": PRODUCT, "platforms": ["x"]})
    ran = client.post("/operator/tick").json()["ran"]
    assert len(ran) == 1
    assert client.post("/operator/tick").json()["ran"] == []


def test_operator_tick_all_auth(client, monkeypatch):
    monkeypatch.delenv("OPERATOR_TICK_SECRET", raising=False)
    assert client.post("/operator/tick/all").status_code == 403
    monkeypatch.setenv("OPERATOR_TICK_SECRET", "op")
    assert client.post("/operator/tick/all").status_code == 403
    assert client.post("/operator/tick/all", headers={"X-Tick-Secret": "nope"}).status_code == 403
    store.create_operator_subscription("alice", name="n", product=PRODUCT, platforms=["x"])
    res = client.post("/operator/tick/all", headers={"X-Tick-Secret": "op"})
    assert res.status_code == 200
    assert len(res.json()["ran"]) == 1
