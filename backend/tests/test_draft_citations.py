"""Tests for draft citation tracking — end-to-end via TestClient.

Covers:
  * cited_snippet_ids gets stamped on every draft from /generate (not just
    the first), so the per-platform attribution is correct.
  * /drafts/{id}/citations returns the snippets, ordered by save sequence.
  * Auth boundary: owners-only access on the citations endpoint.
  * Drafts produced without research return an empty list.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import main, store
from app.research import Snippet


def _agent_returning(monkeypatch, plan_dict, drafts_per_platform="d"):
    """Patch SocialAgent.run so /generate returns deterministic content."""

    def fake_run(self, product, platforms, *, research_context=None):
        return {
            "plan": plan_dict,
            "posts": {
                p: {
                    "draft": "raw",
                    "feedback": "LGTM",
                    "final": f"{drafts_per_platform}-{p}",
                }
                for p in platforms
            },
        }

    monkeypatch.setattr(main.SocialAgent, "run", fake_run)


def test_generate_with_research_attributes_to_every_draft(monkeypatch):
    """The bug we're fixing: /generate with research used to mark only the
    first draft as 'used' — leaving the other 14 platform drafts with no
    audit trail. After the fix, every draft carries the same cited list."""
    _agent_returning(
        monkeypatch,
        {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
    )
    client = TestClient(main.app)
    uid = client.get("/me").json()["user_id"]

    # Bank some snippets so the research path has data to surface.
    store.upsert_snippets(
        uid,
        [
            Snippet(source="hn", url="https://e.com/1", title="t1", score=0.9),
            Snippet(source="reddit", url="https://e.com/2", title="t2", score=0.7),
        ],
    )

    res = client.post(
        "/generate",
        json={"product": "a sample product blurb", "platforms": ["x", "linkedin"], "use_research": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["research_used"] == 2
    # Every draft must carry the full cited list — not just the first.
    cited_lists = [d["cited_snippet_ids"] for d in body["drafts"]]
    assert len(cited_lists) == 2
    assert all(len(c) == 2 for c in cited_lists)
    assert cited_lists[0] == cited_lists[1]


def test_generate_without_research_leaves_citations_empty(monkeypatch):
    _agent_returning(
        monkeypatch,
        {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
    )
    client = TestClient(main.app)
    res = client.post(
        "/generate",
        json={"product": "a sample product blurb", "platforms": ["x"], "use_research": False},
    )
    assert res.status_code == 200
    drafts = res.json()["drafts"]
    assert drafts[0]["cited_snippet_ids"] == []


def test_citations_endpoint_returns_snippets_in_save_order(monkeypatch):
    _agent_returning(
        monkeypatch,
        {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
    )
    client = TestClient(main.app)
    uid = client.get("/me").json()["user_id"]

    # Bank in a specific order. ``top_snippets_for_agent`` returns by score
    # desc, so URL 2 (score 0.95) will be cited before URL 1 (score 0.5).
    store.upsert_snippets(
        uid,
        [
            Snippet(source="hn", url="https://e.com/low", title="low", score=0.5),
            Snippet(source="reddit", url="https://e.com/high", title="high", score=0.95),
        ],
    )

    gen = client.post(
        "/generate",
        json={"product": "a sample product blurb", "platforms": ["x"], "use_research": True},
    )
    draft_id = gen.json()["drafts"][0]["id"]

    res = client.get(f"/drafts/{draft_id}/citations")
    assert res.status_code == 200
    body = res.json()
    titles = [s["title"] for s in body["snippets"]]
    assert titles == ["high", "low"]


def test_citations_endpoint_404_for_unknown_draft():
    client = TestClient(main.app)
    res = client.get("/drafts/does-not-exist/citations")
    assert res.status_code == 404


def test_citations_endpoint_owners_only(monkeypatch):
    """Citations must enforce the same auth boundary as /drafts/{id}."""
    _agent_returning(
        monkeypatch,
        {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
    )

    # Manually create a draft owned by a *different* user. We poke the store
    # directly because TestClient is anchored to the dev-mode user.
    fake_result = {
        "plan": {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
        "posts": {"x": {"draft": "r", "feedback": "f", "final": "f"}},
    }
    drafts = store.save_drafts("other-user", "p" * 20, fake_result)
    other_id = drafts[0]["id"]

    client = TestClient(main.app)  # auths as the dev-mode user, not "other-user"
    res = client.get(f"/drafts/{other_id}/citations")
    assert res.status_code == 404


def test_variations_with_research_carries_citations(monkeypatch):
    def fake_variations(self, product, platform, n=5, *, research_context=None):
        return [{"angle": f"angle-{i}", "content": f"c-{i}"} for i in range(n)]

    monkeypatch.setattr(main.SocialAgent, "variations", fake_variations)
    client = TestClient(main.app)
    uid = client.get("/me").json()["user_id"]

    store.upsert_snippets(
        uid, [Snippet(source="hn", url="https://e.com/v", title="v", score=0.5)]
    )

    res = client.post(
        "/variations",
        json={"product": "a sample product blurb", "platform": "x", "count": 3, "use_research": True},
    )
    assert res.status_code == 200
    drafts = res.json()["drafts"]
    assert len(drafts) == 3
    assert all(len(d["cited_snippet_ids"]) == 1 for d in drafts)
