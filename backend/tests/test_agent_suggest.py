"""Tests for ``SocialAgent.suggest_research_queries``.

Groq is mocked at the ``_chat`` boundary — every model call funnels through
that one method, so monkeypatching it covers all paths without spinning up
the real client.
"""

from __future__ import annotations

import json

import pytest

from app.agent import SocialAgent


def _agent_with_chat_returning(monkeypatch, payload):
    """Build a SocialAgent whose ``_chat`` returns ``payload`` (dict → JSON-str)."""
    agent = SocialAgent.__new__(SocialAgent)  # skip __init__ → no Groq() construction
    agent.client = None  # type: ignore[assignment]
    agent.model = "test-model"
    monkeypatch.setattr(agent, "_chat", lambda *a, **kw: json.dumps(payload))
    return agent


def test_suggest_returns_strings(monkeypatch):
    agent = _agent_with_chat_returning(
        monkeypatch,
        {"queries": ["ai agents", "content automation", "indie hackers", "llm tooling", "devrel"]},
    )
    out = agent.suggest_research_queries("a product description that's long enough", n=5)
    assert out == ["ai agents", "content automation", "indie hackers", "llm tooling", "devrel"]


def test_suggest_dedupes_case_insensitive(monkeypatch):
    agent = _agent_with_chat_returning(
        monkeypatch,
        {"queries": ["AI Agents", "ai agents", "  AI agents  ", "content automation"]},
    )
    out = agent.suggest_research_queries("p" * 20, n=5)
    # First-seen wins on dedup; trim is applied; only two distinct phrases survive.
    assert out == ["AI Agents", "content automation"]


def test_suggest_drops_non_strings_and_blanks(monkeypatch):
    agent = _agent_with_chat_returning(
        monkeypatch,
        {"queries": ["good one", "", "   ", {"nested": "obj"}, 42, "another good one"]},
    )
    out = agent.suggest_research_queries("p" * 20, n=5)
    assert out == ["good one", "another good one"]


def test_suggest_caps_at_n(monkeypatch):
    agent = _agent_with_chat_returning(
        monkeypatch,
        {"queries": [f"q{i}" for i in range(20)]},
    )
    out = agent.suggest_research_queries("p" * 20, n=3)
    assert out == ["q0", "q1", "q2"]


def test_suggest_n_bounds():
    agent = SocialAgent.__new__(SocialAgent)
    agent.client = None  # type: ignore[assignment]
    agent.model = "test-model"
    with pytest.raises(ValueError):
        agent.suggest_research_queries("p" * 20, n=0)
    with pytest.raises(ValueError):
        agent.suggest_research_queries("p" * 20, n=11)


def test_suggest_handles_missing_queries_key(monkeypatch):
    agent = _agent_with_chat_returning(monkeypatch, {})
    assert agent.suggest_research_queries("p" * 20, n=5) == []
