"""Tests for the Eva operator — autonomous experiment picker + audit row.

Covers:
  * select_experiment_snippets cold-start (no outcomes yet) → falls back to
    score-only ordering.
  * select_experiment_snippets warm path → reorders by leaderboard winners.
  * operator.run end-to-end with a stubbed agent: logs OperatorRun, saves
    drafts with citations, marks snippets used, no real Groq call.
  * operator.run failure path: OperatorRun ends up in ``failed`` status with
    the exception captured (no ``pending`` rows leak).
  * /operator/run, /operator/runs, /operator/runs/{id} endpoints.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import main, operator, store
from app.research import Snippet


def _stub_agent(monkeypatch, *, plan_dict=None, raise_exc: Exception | None = None):
    """Patch SocialAgent.run so the operator does not touch Groq."""

    plan_dict = plan_dict or {
        "audience": "a",
        "angle": "b",
        "key_points": ["c"],
        "tone": "d",
        "cta": "e",
    }

    def fake_run(self, product, platforms, *, research_context=None):
        if raise_exc is not None:
            raise raise_exc
        return {
            "plan": plan_dict,
            "posts": {
                p: {"draft": "raw", "feedback": "ok", "final": f"final-{p}"}
                for p in platforms
            },
        }

    monkeypatch.setattr(main.SocialAgent, "run", fake_run)


# ---------------------------------------------------------------------------
# picker
# ---------------------------------------------------------------------------


def test_select_experiment_cold_start_returns_top_score():
    uid = "u-cold"
    store.upsert_snippets(
        uid,
        [
            Snippet(source="hn", url="https://e.com/a", title="A", score=0.9, query="q"),
            Snippet(source="hn", url="https://e.com/b", title="B", score=0.5, query="q"),
        ],
    )
    pick = store.select_experiment_snippets(uid, limit=2)
    assert [s["title"] for s in pick["snippets"]] == ["A", "B"]
    assert pick["leaderboard_used"] is False
    assert pick["winning_sources"] == []


def test_select_experiment_cold_start_empty_when_no_snippets():
    pick = store.select_experiment_snippets("u-none", limit=5)
    assert pick == {"snippets": [], "leaderboard_used": False, "winning_sources": []}


def test_select_experiment_reorders_by_leaderboard():
    """A lower-score snippet from a winning source should outrank a higher-
    score snippet from a source that has never produced engagement."""
    uid = "u-warm"

    # Step 1 — populate engagement history: an OLD HN/agents snippet was cited
    # by a draft that earned 50 likes.  This makes HN/agents a leaderboard
    # winner.  The old snippet then ages out of the unused pool naturally
    # (used_in_draft_id is set), so the picker won't see it again.
    old = store.upsert_snippets(
        uid,
        [Snippet(source="hn", url="https://hn.example/old", title="HN-old", score=0.9, query="agents")],
    )
    fake_result = {
        "plan": {"audience": "a", "angle": "b", "key_points": ["c"], "tone": "d", "cta": "e"},
        "posts": {"x": {"draft": "r", "feedback": "f", "final": "f"}},
    }
    drafts = store.save_drafts(uid, "p" * 20, fake_result, cited_snippet_ids=[old[0]["id"]])
    store.mark_snippets_used(uid, [old[0]["id"]], drafts[0]["id"])
    store.record_outcome(uid, drafts[0]["id"], metric_kind="likes", metric_value=50)

    # Step 2 — fresh fetch brings in a NEW HN snippet (mid-score) and a NEW
    # Reddit snippet (high-score).  The picker only sees unused rows.
    store.upsert_snippets(
        uid,
        [
            Snippet(source="hn", url="https://hn.example/new", title="HN-new", score=0.4, query="agents"),
            Snippet(source="reddit", url="https://rd.example/new", title="RD-new", score=0.95, query="agents"),
        ],
    )

    pick = store.select_experiment_snippets(uid, limit=5, weight_by_leaderboard=True)
    sources = [s["source"] for s in pick["snippets"]]
    # Boost should pull HN ahead of Reddit despite Reddit's higher raw score.
    assert sources.index("hn") < sources.index("reddit")
    assert pick["leaderboard_used"] is True


def test_select_experiment_respects_weight_flag():
    uid = "u-noweight"
    store.upsert_snippets(
        uid,
        [
            Snippet(source="hn", url="https://e.com/a", title="A", score=0.9, query="q"),
        ],
    )
    pick = store.select_experiment_snippets(uid, weight_by_leaderboard=False)
    assert pick["leaderboard_used"] is False


# ---------------------------------------------------------------------------
# operator.run
# ---------------------------------------------------------------------------


def test_operator_run_logs_audit_row_and_saves_drafts(monkeypatch):
    _stub_agent(monkeypatch)
    uid = "u-run"
    store.upsert_snippets(
        uid,
        [Snippet(source="hn", url="https://e.com/a", title="A", score=0.9, query="q")],
    )

    res = operator.run(
        uid,
        product="a sample product blurb",
        platforms=["x"],
    )
    assert res.run_id
    assert len(res.drafts) == 1
    assert len(res.picked_snippets) == 1
    # Audit row exists, is ok, and points at the same draft.
    run_row = store.get_operator_run(uid, res.run_id)
    assert run_row["status"] == "ok"
    assert run_row["draft_ids"] == [res.drafts[0]["id"]]
    assert run_row["cited_snippet_ids"] == [res.picked_snippets[0]["id"]]
    assert "cold-start" in (run_row["notes"] or "")


def test_operator_run_ungrounded_when_no_snippets(monkeypatch):
    _stub_agent(monkeypatch)
    uid = "u-empty"
    res = operator.run(uid, product="a sample product blurb", platforms=["x"])
    assert res.picked_snippets == []
    assert res.leaderboard_used is False
    run_row = store.get_operator_run(uid, res.run_id)
    assert run_row["status"] == "ok"
    assert run_row["cited_snippet_ids"] == []
    assert "ungrounded" in (run_row["notes"] or "")


def test_operator_run_failure_marks_run_failed(monkeypatch):
    _stub_agent(monkeypatch, raise_exc=RuntimeError("boom"))
    uid = "u-fail"

    try:
        operator.run(uid, product="a sample product blurb", platforms=["x"])
    except RuntimeError:
        pass
    else:
        raise AssertionError("operator.run should re-raise")

    runs = store.list_operator_runs(uid)
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert "RuntimeError" in (runs[0]["error"] or "")
    assert runs[0]["completed_at"]  # closed out, not left pending


def test_operator_run_rejects_invalid_platform(monkeypatch):
    _stub_agent(monkeypatch)
    try:
        operator.run("u-bad-plat", product="a sample product blurb", platforms=["nope"])
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown platform")


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


def test_post_operator_run_endpoint(monkeypatch):
    _stub_agent(monkeypatch)
    client = TestClient(main.app)

    res = client.post(
        "/operator/run",
        json={"product": "a sample product blurb", "platforms": ["x", "linkedin"]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["operator_run_id"]
    assert len(body["drafts"]) == 2
    assert "winning_sources" in body
    assert body["leaderboard_used"] is False  # cold-start


def test_post_operator_run_endpoint_rejects_invalid_platform(monkeypatch):
    _stub_agent(monkeypatch)
    client = TestClient(main.app)
    res = client.post(
        "/operator/run",
        json={"product": "a sample product blurb", "platforms": ["nope"]},
    )
    assert res.status_code == 400


def test_list_operator_runs_endpoint(monkeypatch):
    _stub_agent(monkeypatch)
    client = TestClient(main.app)
    for _ in range(3):
        client.post("/operator/run", json={"product": "a sample product blurb", "platforms": ["x"]})

    res = client.get("/operator/runs?limit=5")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 3
    assert all(r["status"] == "ok" for r in rows)


def test_get_operator_run_404(monkeypatch):
    client = TestClient(main.app)
    res = client.get("/operator/runs/does-not-exist")
    assert res.status_code == 404


def test_operator_runs_owners_only(monkeypatch):
    _stub_agent(monkeypatch)
    other_run = store.start_operator_run(
        "user-other",
        product="x" * 20,
        platforms=["x"],
        weight_by_leaderboard=False,
        leaderboard_metric="likes",
    )
    client = TestClient(main.app)
    res = client.get(f"/operator/runs/{other_run['id']}")
    assert res.status_code == 404
