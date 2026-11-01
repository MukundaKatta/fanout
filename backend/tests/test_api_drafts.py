"""Route tests for the draft lifecycle: /generate, /variations, /drafts,
review checkpoints, queue/schedule, /queue polling, /posted, outcomes.

Groq is never hit — ``SocialAgent`` methods are monkeypatched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main, store
from app.research import Snippet

PRODUCT = "A product blurb long enough to validate"
PLAN = {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"}


@pytest.fixture
def client(monkeypatch):
    # Avoid constructing a real Groq client.
    monkeypatch.setattr(main.SocialAgent, "__init__", lambda self, *a, **k: None)

    def fake_run(self, product, platforms, *, research_context=None):
        fake_run.research_context = research_context
        return {
            "plan": PLAN,
            "posts": {p: {"draft": "raw", "feedback": "LGTM", "final": f"final-{p}"} for p in platforms},
        }

    def fake_variations(self, product, platform, n=5, *, research_context=None):
        fake_variations.research_context = research_context
        return [{"angle": f"angle-{i}", "content": f"{platform}-{i}"} for i in range(n)]

    monkeypatch.setattr(main.SocialAgent, "run", fake_run)
    monkeypatch.setattr(main.SocialAgent, "variations", fake_variations)
    c = TestClient(main.app)
    c.fake_run = fake_run
    c.fake_variations = fake_variations
    return c


def _uid(client):
    return client.get("/me").json()["user_id"]


def _one_draft(client, platform="x"):
    res = client.post("/variations", json={"product": PRODUCT, "platform": platform, "count": 1})
    assert res.status_code == 200
    return res.json()["drafts"][0]


# --- health ------------------------------------------------------------------


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


# --- /generate ---------------------------------------------------------------


def test_generate_default_platforms_creates_one_draft_each(client):
    res = client.post("/generate", json={"product": PRODUCT})
    assert res.status_code == 200
    body = res.json()
    assert body["plan"] == PLAN
    assert body["research_used"] == 0
    assert {d["platform"] for d in body["drafts"]} == set(main.PLATFORMS)
    assert all(d["status"] == "pending" for d in body["drafts"])
    assert client.fake_run.research_context is None


def test_generate_rejects_invalid_platforms(client):
    res = client.post("/generate", json={"product": PRODUCT, "platforms": ["x", "myspace"]})
    assert res.status_code == 400
    assert "myspace" in res.json()["detail"]


def test_generate_validates_product_length(client):
    assert client.post("/generate", json={"product": "short"}).status_code == 422


def test_generate_use_research_without_snippets_passes_no_context(client):
    res = client.post("/generate", json={"product": PRODUCT, "platforms": ["x"], "use_research": True})
    assert res.status_code == 200
    assert res.json()["research_used"] == 0
    assert client.fake_run.research_context is None


def test_generate_use_research_marks_snippets_used(client):
    uid = _uid(client)
    store.upsert_snippets(uid, [Snippet(source="hn", url="https://e.com/a", title="Hot thread", score=0.9)])
    res = client.post("/generate", json={"product": PRODUCT, "platforms": ["x"], "use_research": True})
    body = res.json()
    assert body["research_used"] == 1
    assert "Hot thread" in client.fake_run.research_context
    # Snippet is consumed → not offered again.
    assert store.top_snippets_for_agent(uid) == []
    used = client.get("/research").json()[0]
    assert used["used_in_draft_id"] == body["drafts"][0]["id"]


# --- /variations -------------------------------------------------------------


def test_variations_saves_angle_as_feedback(client):
    res = client.post("/variations", json={"product": PRODUCT, "platform": "linkedin", "count": 3})
    assert res.status_code == 200
    drafts = res.json()["drafts"]
    assert [d["content"] for d in drafts] == ["linkedin-0", "linkedin-1", "linkedin-2"]
    assert [d["feedback"] for d in drafts] == ["angle-0", "angle-1", "angle-2"]
    assert res.json()["research_used"] == 0


def test_variations_rejects_unknown_platform(client):
    res = client.post("/variations", json={"product": PRODUCT, "platform": "myspace"})
    assert res.status_code == 400


@pytest.mark.parametrize("count", [0, 9])
def test_variations_count_bounds(client, count):
    res = client.post("/variations", json={"product": PRODUCT, "platform": "x", "count": count})
    assert res.status_code == 422


def test_variations_with_research(client):
    uid = _uid(client)
    store.upsert_snippets(uid, [Snippet(source="devto", url="https://e.com/b", title="Dev post", score=0.5)])
    res = client.post(
        "/variations", json={"product": PRODUCT, "platform": "x", "count": 2, "use_research": True}
    )
    body = res.json()
    assert body["research_used"] == 1
    assert all(len(d["cited_snippet_ids"]) == 1 for d in body["drafts"])
    assert "Dev post" in client.fake_variations.research_context


# --- /drafts CRUD ------------------------------------------------------------


def test_list_get_and_filter_drafts(client):
    d = _one_draft(client)
    assert [x["id"] for x in client.get("/drafts").json()] == [d["id"]]
    assert client.get("/drafts", params={"status": "pending"}).json()[0]["id"] == d["id"]
    assert client.get("/drafts", params={"status": "posted"}).json() == []
    assert client.get(f"/drafts/{d['id']}").json()["content"] == d["content"]


def test_get_missing_draft_404(client):
    assert client.get("/drafts/nope").status_code == 404


def test_patch_draft_content(client):
    d = _one_draft(client)
    res = client.patch(f"/drafts/{d['id']}", params={"content": "edited"})
    assert res.status_code == 200
    assert res.json()["content"] == "edited"
    assert client.get(f"/drafts/{d['id']}").json()["content"] == "edited"
    assert client.patch("/drafts/nope", params={"content": "x"}).status_code == 404


def test_other_users_draft_is_not_found(client):
    other = store.save_variations("someone-else", PRODUCT, "x", [{"angle": "a", "content": "c"}])[0]
    assert client.get(f"/drafts/{other['id']}").status_code == 404
    assert client.patch(f"/drafts/{other['id']}", params={"content": "pwn"}).status_code == 404
    assert client.post(f"/drafts/{other['id']}/queue").status_code == 404
    assert client.post("/posted", json={"draft_id": other["id"]}).status_code == 404


# --- adapter contract --------------------------------------------------------


def test_adapter_contract(client):
    res = client.get("/platforms/x/adapter")
    assert res.status_code == 200
    body = res.json()
    assert body["adapter"]["platform"] == "x"
    assert body["adapter"]["composer"] == "content-x.js"
    assert client.get("/platforms/email/adapter").status_code == 404


# --- review checkpoints ------------------------------------------------------


def test_review_checkpoint_high_confidence_on_autopost_platform(client):
    d = _one_draft(client, "x")  # x: requiresApproval False
    res = client.post(f"/drafts/{d['id']}/review-checkpoint", json={"confidence": 0.95})
    assert res.status_code == 200
    body = res.json()
    assert body["checkpoint"]["requires_review"] is False
    assert body["checkpoint"]["recommended_action"] == "queue"
    assert body["draft"]["status"] == "pending"


def test_review_checkpoint_low_confidence_requires_review_and_persists(client):
    d = _one_draft(client, "x")
    res = client.post(
        f"/drafts/{d['id']}/review-checkpoint", json={"confidence": 0.3, "notes": "unsure"}
    )
    body = res.json()
    assert body["checkpoint"]["requires_review"] is True
    assert body["checkpoint"]["recommended_action"] == "human_review"
    assert body["draft"]["status"] == "review_required"
    stored = client.get(f"/drafts/{d['id']}").json()
    assert stored["status"] == "review_required"
    assert stored["plan"]["review"] == {"confidence": 0.3, "notes": "unsure", "requires_review": True}


def test_review_checkpoint_platform_requiring_approval(client):
    d = _one_draft(client, "linkedin")  # requiresApproval True
    body = client.post(f"/drafts/{d['id']}/review-checkpoint", json={"confidence": 0.99}).json()
    assert body["checkpoint"]["requires_review"] is True


def test_review_checkpoint_on_draft_with_existing_plan_persists(client):
    """Drafts from /generate already carry a plan dict; the review block must
    still be written to the DB (regression: in-place JSON mutation was lost)."""
    d = client.post("/generate", json={"product": PRODUCT, "platforms": ["x"]}).json()["drafts"][0]
    client.post(f"/drafts/{d['id']}/review-checkpoint", json={"confidence": 0.2, "notes": "n"})
    stored = client.get(f"/drafts/{d['id']}").json()
    assert stored["plan"]["audience"] == "a"
    assert stored["plan"]["review"]["requires_review"] is True


def test_review_checkpoint_validation_and_404(client):
    d = _one_draft(client)
    assert client.post(f"/drafts/{d['id']}/review-checkpoint", json={"confidence": 1.5}).status_code == 422
    assert client.post("/drafts/nope/review-checkpoint", json={"confidence": 0.5}).status_code == 404


def test_approve_review_queues_draft(client):
    d = _one_draft(client, "linkedin")
    client.post(f"/drafts/{d['id']}/review-checkpoint", json={"confidence": 0.2})
    res = client.post(f"/drafts/{d['id']}/approve", json={"reviewer": "mk"})
    assert res.status_code == 200
    assert res.json()["status"] == "queued"
    stored = client.get(f"/drafts/{d['id']}").json()
    assert stored["status"] == "queued"
    assert stored["plan"]["review"]["approved_by"] == "mk"
    assert stored["plan"]["review"]["requires_review"] is False
    assert stored["plan"]["review"]["confidence"] == 0.2


def test_approve_review_validation_and_404(client):
    d = _one_draft(client)
    assert client.post(f"/drafts/{d['id']}/approve", json={"reviewer": "m"}).status_code == 422
    assert client.post("/drafts/nope/approve", json={"reviewer": "mk"}).status_code == 404


# --- queue / schedule / poll / posted ---------------------------------------


def test_queue_then_poll_claims_once(client):
    d = _one_draft(client, "x")
    assert client.post(f"/drafts/{d['id']}/queue").json()["status"] == "queued"
    first = client.get("/queue").json()
    assert first == [{"draft_id": d["id"], "platform": "x", "content": d["content"]}]
    # Claimed drafts move to "posting" and aren't handed out again.
    assert client.get("/queue").json() == []
    assert client.get(f"/drafts/{d['id']}").json()["status"] == "posting"


def test_queue_missing_404(client):
    assert client.post("/drafts/nope/queue").status_code == 404


def test_queue_filters_by_platform(client):
    dx = _one_draft(client, "x")
    dl = _one_draft(client, "linkedin")
    client.post("/queue-bulk", json={"draft_ids": [dx["id"], dl["id"]]})
    assert [q["draft_id"] for q in client.get("/queue", params={"platform": "linkedin"}).json()] == [dl["id"]]
    assert [q["draft_id"] for q in client.get("/queue").json()] == [dx["id"]]


def test_queue_bulk_skips_unknown_ids(client):
    d = _one_draft(client)
    res = client.post("/queue-bulk", json={"draft_ids": [d["id"], "nope"]})
    assert [q["id"] for q in res.json()["queued"]] == [d["id"]]


def test_schedule_future_not_due_past_due(client):
    future = _one_draft(client)
    past = _one_draft(client)
    later = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    earlier = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    r1 = client.post(f"/drafts/{future['id']}/schedule", json={"scheduled_at": later})
    r2 = client.post(f"/drafts/{past['id']}/schedule", json={"scheduled_at": earlier})
    assert r1.json()["status"] == "scheduled" and r1.json()["scheduled_at"]
    assert r2.status_code == 200
    due = client.get("/queue").json()
    assert [q["draft_id"] for q in due] == [past["id"]]


def test_schedule_naive_datetime_treated_as_utc(client):
    d = _one_draft(client)
    naive = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None).isoformat()
    assert client.post(f"/drafts/{d['id']}/schedule", json={"scheduled_at": naive}).status_code == 200
    assert [q["draft_id"] for q in client.get("/queue").json()] == [d["id"]]


def test_cancel_schedule(client):
    d = _one_draft(client)
    later = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    client.post(f"/drafts/{d['id']}/schedule", json={"scheduled_at": later})
    res = client.delete(f"/drafts/{d['id']}/schedule")
    assert res.json()["status"] == "pending"
    assert res.json()["scheduled_at"] is None
    assert client.delete("/drafts/nope/schedule").status_code == 404
    assert client.post("/drafts/nope/schedule", json={"scheduled_at": later}).status_code == 404


def test_queue_now_clears_schedule(client):
    d = _one_draft(client)
    later = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    client.post(f"/drafts/{d['id']}/schedule", json={"scheduled_at": later})
    res = client.post(f"/drafts/{d['id']}/queue").json()
    assert res["status"] == "queued" and res["scheduled_at"] is None


def test_posted_success_and_failure(client):
    ok = _one_draft(client)
    bad = _one_draft(client)
    res = client.post("/posted", json={"draft_id": ok["id"], "post_url": "https://x.com/1"})
    assert res.status_code == 200
    assert res.json()["status"] == "posted"
    assert res.json()["post_url"] == "https://x.com/1"

    res = client.post("/posted", json={"draft_id": bad["id"], "error": "composer missing"})
    assert res.json()["status"] == "failed"
    assert res.json()["error"] == "composer missing"


def test_posted_after_failure_clears_error(client):
    d = _one_draft(client)
    client.post("/posted", json={"draft_id": d["id"], "error": "boom"})
    res = client.post("/posted", json={"draft_id": d["id"], "post_url": "https://x.com/2"}).json()
    assert res["status"] == "posted" and res["error"] is None


def test_posted_unknown_draft_404(client):
    assert client.post("/posted", json={"draft_id": "nope"}).status_code == 404
    assert client.post("/posted", json={"draft_id": "nope", "error": "e"}).status_code == 404


# --- outcomes routes ---------------------------------------------------------


def test_outcomes_routes_404_for_missing_draft(client):
    assert client.get("/drafts/nope/outcomes").status_code == 404
    res = client.post("/drafts/nope/outcomes", json={"metric_kind": "likes", "metric_value": 1})
    assert res.status_code == 404


def test_outcomes_validation(client):
    d = _one_draft(client)
    # metric_kind is an open set on purpose — unknown kinds are accepted.
    ok = client.post(f"/drafts/{d['id']}/outcomes", json={"metric_kind": "bookmarks", "metric_value": 1})
    assert ok.status_code == 201
    neg = client.post(f"/drafts/{d['id']}/outcomes", json={"metric_kind": "likes", "metric_value": -1})
    assert neg.status_code == 422
    empty = client.post(f"/drafts/{d['id']}/outcomes", json={"metric_kind": "", "metric_value": 1})
    assert empty.status_code == 422


def test_outcomes_roundtrip(client):
    d = _one_draft(client)
    for v in (3, 7):
        r = client.post(f"/drafts/{d['id']}/outcomes", json={"metric_kind": "likes", "metric_value": v})
        assert r.status_code == 201
    body = client.get(f"/drafts/{d['id']}/outcomes").json()
    assert body["draft_id"] == d["id"]
    assert len(body["timeline"]) == 2


def test_source_leaderboard_limit_bounds(client):
    assert client.get("/research/sources/leaderboard", params={"limit": 0}).status_code == 422
    assert client.get("/research/sources/leaderboard", params={"limit": 51}).status_code == 422
    res = client.get("/research/sources/leaderboard")
    assert res.json() == {"metric": "likes", "rows": []}
