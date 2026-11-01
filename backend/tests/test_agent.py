"""Unit tests for ``SocialAgent`` with a scripted fake Groq client.

No network: every ``chat.completions.create`` call pops the next canned
response off a queue and records the kwargs so we can assert on prompts.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agent import ANGLES, PLATFORM_RULES, PLATFORMS, Plan, SocialAgent


class FakeGroq:
    def __init__(self, responses: list[str | None]):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = self._responses.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


PLAN_JSON = json.dumps(
    {
        "audience": "indie devs",
        "angle": "ship faster",
        "key_points": ["one", "two", "three"],
        "tone": "casual",
        "cta": "try it",
    }
)


def _agent(responses):
    client = FakeGroq(responses)
    return SocialAgent(client=client, model="test-model"), client


def test_platforms_and_rules_are_in_sync():
    assert len(PLATFORMS) == 15
    assert set(PLATFORMS) == set(PLATFORM_RULES)


def test_plan_as_prompt_block_includes_every_field():
    p = Plan(audience="a", angle="b", key_points=["k1", "k2"], tone="t", cta="c")
    block = p.as_prompt_block()
    for frag in ("Audience: a", "Angle: b", "- k1", "- k2", "Tone: t", "CTA: c"):
        assert frag in block


def test_chat_passes_model_and_json_mode():
    agent, client = _agent(['{"x": 1}', "plain"])
    assert agent._chat("sys", "usr", json_mode=True, temperature=0.1) == '{"x": 1}'
    call = client.calls[0]
    assert call["model"] == "test-model"
    assert call["temperature"] == 0.1
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    agent._chat("s", "u")
    assert "response_format" not in client.calls[1]


def test_chat_returns_empty_string_on_none_content():
    agent, _ = _agent([None])
    assert agent._chat("s", "u") == ""


def test_plan_parses_json_and_injects_research_into_system_prompt():
    agent, client = _agent([PLAN_JSON])
    plan = agent.plan("A product", research_context="SIGNAL-XYZ")
    assert plan.audience == "indie devs"
    assert plan.key_points == ["one", "two", "three"]
    assert "SIGNAL-XYZ" in client.calls[0]["messages"][0]["content"]


def test_plan_without_research_has_no_live_signals():
    agent, client = _agent([PLAN_JSON])
    agent.plan("A product")
    assert "Live signals" not in client.calls[0]["messages"][0]["content"]


def test_write_rejects_unknown_platform():
    agent, _ = _agent([])
    with pytest.raises(ValueError, match="Unknown platform"):
        agent.write("myspace", "p", Plan("a", "b", ["c"], "d", "e"))


def test_write_strips_and_includes_research_in_user_prompt():
    agent, client = _agent(["  hello world  \n"])
    out = agent.write("x", "prod", Plan("a", "b", ["c"], "d", "e"), research_context="SIG")
    assert out == "hello world"
    assert "SIG" in client.calls[0]["messages"][1]["content"]
    assert PLATFORM_RULES["x"] in client.calls[0]["messages"][0]["content"]


def test_refine_short_circuits_on_lgtm():
    agent, client = _agent([])
    assert agent.refine("x", "draft", "lgtm, ship it") == "draft"
    assert client.calls == []


def test_refine_calls_model_on_feedback():
    agent, client = _agent(["revised "])
    assert agent.refine("x", "draft", "1. shorter") == "revised"
    assert "1. shorter" in client.calls[0]["messages"][1]["content"]


def test_run_full_pipeline_per_platform():
    # plan, then per platform: write, critique, (refine unless LGTM)
    agent, client = _agent(
        [
            PLAN_JSON,
            "x draft",
            "LGTM",  # x: no refine call
            "li draft",
            "fix the hook",
            "li final",
        ]
    )
    result = agent.run("prod", platforms=("x", "linkedin"))
    assert result["plan"]["audience"] == "indie devs"
    assert result["posts"]["x"] == {"draft": "x draft", "feedback": "LGTM", "final": "x draft"}
    assert result["posts"]["linkedin"]["final"] == "li final"
    assert len(client.calls) == 6


def test_variations_validates_inputs():
    agent, _ = _agent([])
    with pytest.raises(ValueError, match="Unknown platform"):
        agent.variations("p", "nope")
    with pytest.raises(ValueError, match="between 1 and 8"):
        agent.variations("p", "x", n=0)
    with pytest.raises(ValueError, match="between 1 and 8"):
        agent.variations("p", "x", n=9)


def test_variations_fills_missing_angles_drops_empty_and_caps():
    payload = {
        "variations": [
            {"angle": "custom", "content": " first "},
            {"content": "second"},  # angle falls back to ANGLES[1]
            {"angle": "empty", "content": "   "},  # dropped
            {"angle": "extra", "content": "over the cap"},  # beyond n
        ]
    }
    agent, client = _agent([json.dumps(payload)])
    out = agent.variations("prod", "x", n=3, research_context="SIG")
    assert out == [
        {"angle": "custom", "content": "first"},
        {"angle": ANGLES[1], "content": "second"},
    ]
    call = client.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert "SIG" in call["messages"][1]["content"]


def test_variations_falls_back_to_generic_angle_past_angle_list():
    n = 7  # more than len(ANGLES)
    payload = {"variations": [{"content": f"c{i}"} for i in range(n)]}
    agent, _ = _agent([json.dumps(payload)])
    out = agent.variations("prod", "x", n=n)
    assert len(out) == n
    assert out[-1]["angle"] == "variation"


def test_suggest_research_queries_dedupes_and_caps():
    payload = {"queries": ["AI agents", "ai agents", "", 42, {"q": "x"}, "  rag evals ", "llm ops", "extra"]}
    agent, client = _agent([json.dumps(payload)])
    out = agent.suggest_research_queries("prod", n=3)
    assert out == ["AI agents", "rag evals", "llm ops"]
    assert client.calls[0]["temperature"] == 0.5


def test_suggest_research_queries_validates_n():
    agent, _ = _agent([])
    with pytest.raises(ValueError):
        agent.suggest_research_queries("p", n=0)
    with pytest.raises(ValueError):
        agent.suggest_research_queries("p", n=11)
