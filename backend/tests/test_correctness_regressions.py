"""Regression tests for bugs found in the correctness review.

One test (or small group) per bug; each fails on the pre-fix code.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main, operator, research, store
from app.agent import SocialAgent
from app.auth import DEV_USER_ID
from app.research import Snippet


def _draft(uid: str = "u-reg", platform: str = "x") -> dict:
    result = {
        "plan": {"audience": "devs", "angle": "a", "key_points": ["k"], "tone": "t", "cta": "c"},
        "posts": {platform: {"draft": "d", "feedback": "f", "final": "hello"}},
    }
    return store.save_drafts(uid, "a product blurb", result)[0]


# --- review checkpoint / approval metadata must persist ---------------------


def test_review_checkpoint_is_persisted():
    d = _draft()
    store.set_review_checkpoint("u-reg", d["id"], 0.4, "needs a softer hook")
    reloaded = store.get_draft("u-reg", d["id"])
    assert reloaded["plan"]["review"] == {
        "confidence": 0.4,
        "notes": "needs a softer hook",
        "requires_review": True,
    }
    # The rest of the plan survives untouched.
    assert reloaded["plan"]["audience"] == "devs"


def test_review_approval_is_persisted():
    d = _draft()
    store.set_review_checkpoint("u-reg", d["id"], 0.4)
    store.approve_review("u-reg", d["id"], "alice")
    reloaded = store.get_draft("u-reg", d["id"])
    assert reloaded["status"] == "queued"
    assert reloaded["plan"]["review"]["approved_by"] == "alice"
    assert reloaded["plan"]["review"]["requires_review"] is False
    assert reloaded["plan"]["review"]["confidence"] == 0.4


# --- overlapping ticks must not double-fire a subscription ------------------


def _stub_agent_run(monkeypatch, calls: list):
    def fake_run(self, product, platforms, *, research_context=None):
        calls.append(product)
        return {
            "plan": {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
            "posts": {p: {"draft": "r", "feedback": "f", "final": f"final-{p}"} for p in platforms},
        }

    monkeypatch.setattr(SocialAgent, "run", fake_run)
    monkeypatch.setattr(SocialAgent, "__init__", lambda self, *a, **k: None)


def test_operator_tick_overlap_runs_each_sub_once(monkeypatch):
    calls: list = []
    _stub_agent_run(monkeypatch, calls)
    store.create_operator_subscription(
        "u-race", name="daily", product="a sample product blurb", platforms=["x"]
    )
    # Tick A and tick B both read the due list before either finished.
    stale_due = store.due_operator_subscriptions()
    assert len(stale_due) == 1
    first = operator.tick_all()
    second = operator._run_due(stale_due, agent=None)
    assert len(first) == 1 and first[0]["error"] is None
    assert second == []
    assert len(calls) == 1
    assert len(store.list_operator_runs("u-race")) == 1


def test_operator_claim_succeeds_again_once_interval_elapses():
    sub = store.create_operator_subscription(
        "u-race", name="hourly", product="a sample product blurb", platforms=["x"], interval_hours=1
    )
    t0 = datetime.now(timezone.utc)
    assert store.claim_operator_subscription(sub, now=t0) is True
    assert store.claim_operator_subscription(sub, now=t0 + timedelta(minutes=30)) is False
    assert store.claim_operator_subscription(sub, now=t0 + timedelta(hours=1, minutes=1)) is True


def test_operator_claim_skips_inactive_sub():
    sub = store.create_operator_subscription(
        "u-race", name="paused", product="a sample product blurb", platforms=["x"], active=False
    )
    assert store.claim_operator_subscription(sub) is False


def test_research_tick_overlap_runs_each_sub_once(monkeypatch):
    calls: list = []

    def fake_research(req):
        calls.append(req)
        return [Snippet(source="hn", url="https://e.com/1", title="t", score=0.5, query="q")]

    monkeypatch.setattr(main, "run_research", fake_research)
    store.create_subscription(DEV_USER_ID, name="s", queries=["q"], rss_feeds=[])
    stale_due = store.due_subscriptions(user_id=DEV_USER_ID)

    client = TestClient(main.app)
    r = client.post("/research/tick")
    assert r.status_code == 200 and len(r.json()["ran"]) == 1

    # A second, overlapping tick that read ``due`` before the first claimed it.
    monkeypatch.setattr(store, "due_subscriptions", lambda **kw: stale_due)
    r = client.post("/research/tick")
    assert r.json()["ran"] == []
    assert len(calls) == 1


# --- PATCH /drafts/{id} takes content in the JSON body ----------------------


def test_patch_draft_accepts_json_body_for_long_content():
    d = _draft(uid=DEV_USER_ID)
    long_content = ("A long-form Medium paragraph with spaces & symbols. " * 600).strip()
    client = TestClient(main.app)
    r = client.patch(f"/drafts/{d['id']}", json={"content": long_content})
    assert r.status_code == 200, r.text
    assert r.json()["content"] == long_content


def test_patch_draft_query_param_still_supported():
    d = _draft(uid=DEV_USER_ID)
    client = TestClient(main.app)
    r = client.patch(f"/drafts/{d['id']}", params={"content": "short edit"})
    assert r.status_code == 200, r.text
    assert r.json()["content"] == "short edit"


def test_patch_draft_requires_content():
    d = _draft(uid=DEV_USER_ID)
    client = TestClient(main.app)
    assert client.patch(f"/drafts/{d['id']}").status_code == 422


# --- LLM output coercion in draft generation --------------------------------


class _FakeAgent(SocialAgent):
    def __init__(self, reply: dict | list):
        self._reply = json.dumps(reply)
        self.model = "fake"

    def _chat(self, system, user, json_mode=False, temperature=0.7):
        return self._reply


def test_plan_key_points_string_is_not_split_into_characters():
    agent = _FakeAgent(
        {"audience": "devs", "angle": "a", "key_points": "fast setup", "tone": "t", "cta": "c"}
    )
    plan = agent.plan("a product blurb")
    assert plan.key_points == ["fast setup"]


def test_plan_tolerates_missing_fields():
    agent = _FakeAgent({"audience": "devs", "key_points": ["one", 2, None]})
    plan = agent.plan("a product blurb")
    assert plan.audience == "devs"
    assert plan.angle == "" and plan.cta == ""
    assert plan.key_points == ["one", "2"]


def test_variations_tolerates_string_and_junk_items():
    agent = _FakeAgent({"variations": ["plain string post", 42, {"angle": "x", "content": " ok "}]})
    out = agent.variations("a product blurb", "x", n=3)
    assert [v["content"] for v in out] == ["plain string post", "ok"]
    assert out[1]["angle"] == "x"


# --- RSS fetch must only open http(s) URLs ----------------------------------


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://example.com/feed.xml", "/etc/hosts", "http://"]
)
def test_fetch_rss_rejects_non_http_urls(monkeypatch, url):
    def boom(*a, **k):
        raise AssertionError("must not open non-http URLs")

    monkeypatch.setattr(research, "_http_get", boom)
    assert research.fetch_rss(url) == []


def test_fetch_rss_allows_https(monkeypatch):
    xml = b"<rss><channel><item><title>T</title><link>https://e.com/a</link></item></channel></rss>"
    monkeypatch.setattr(research, "_http_get", lambda url, timeout=5.0: xml)
    out = research.fetch_rss("https://e.com/feed.xml")
    assert [s.url for s in out] == ["https://e.com/a"]


# --- snippet columns are clamped to their DB widths -------------------------


def test_upsert_snippets_clamps_query_and_author():
    long_feed = "https://example.com/feed?" + "x" * 400
    snip = Snippet(
        source="rss", url="https://e.com/p", title="t", author="a" * 300, query=long_feed
    )
    [row] = store.upsert_snippets("u-len", [snip])
    assert len(row["query"]) == 256
    assert len(row["author"]) == 128
    # Refresh path clamps too.
    [row] = store.upsert_snippets("u-len", [snip])
    assert len(row["author"]) == 128


# --- /research limit bounds --------------------------------------------------


@pytest.mark.parametrize("limit", [-1, 0, 100000])
def test_research_list_rejects_out_of_range_limit(limit):
    client = TestClient(main.app)
    assert client.get("/research", params={"limit": limit}).status_code == 422


def test_research_list_default_limit_ok():
    client = TestClient(main.app)
    assert client.get("/research").status_code == 200
