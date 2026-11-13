"""Edge-case tests for the research source fetchers and helpers.

Complements ``test_research.py``: focuses on failure paths (network errors,
malformed payloads), parser fallbacks, and the stdlib HTTP shim. All
network access is stubbed — ``urlopen`` / ``_http_get`` never hit the wire.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

from app import research
from app.research import ResearchRequest, Snippet


def _raise(exc):
    def f(*a, **k):
        raise exc

    return f


# --- HTTP shim ---------------------------------------------------------------


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_get_sets_user_agent_and_timeout(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["ua"] = req.get_header("User-agent")
        seen["url"] = req.full_url
        seen["timeout"] = timeout
        return _FakeResp(b'{"ok": true}')

    monkeypatch.setattr(research.urllib.request, "urlopen", fake_urlopen)
    assert research._http_get_json("https://example.com/x", timeout=1.5) == {"ok": True}
    assert seen == {"ua": research.USER_AGENT, "url": "https://example.com/x", "timeout": 1.5}


# --- network failures degrade to [] -----------------------------------------


@pytest.mark.parametrize(
    "exc",
    [urllib.error.URLError("down"), TimeoutError(), OSError("reset"), json.JSONDecodeError("x", "", 0)],
)
@pytest.mark.parametrize("fetch", [research.fetch_hn, research.fetch_devto, research.fetch_reddit])
def test_json_fetchers_swallow_network_errors(monkeypatch, fetch, exc):
    monkeypatch.setattr(research, "_http_get_json", _raise(exc))
    assert fetch("agents") == []


def test_rss_swallows_network_and_parse_errors(monkeypatch):
    monkeypatch.setattr(research, "_http_get", _raise(urllib.error.URLError("down")))
    assert research.fetch_rss("https://f/rss") == []
    monkeypatch.setattr(research, "_http_get", lambda url, timeout=5.0: b"<not-xml")
    assert research.fetch_rss("https://f/rss") == []


def test_blank_queries_short_circuit_without_network(monkeypatch):
    monkeypatch.setattr(research, "_http_get_json", _raise(AssertionError("no network")))
    assert research.fetch_hn("   ") == []
    assert research.fetch_reddit("") == []
    assert research.fetch_devto("!!!") == []  # sanitises to empty tag


# --- payload shapes ----------------------------------------------------------


def test_devto_non_list_payload_and_missing_fields(monkeypatch):
    monkeypatch.setattr(research, "_http_get_json", lambda url: {"error": "rate limited"})
    assert research.fetch_devto("ai") == []

    seen = {}

    def payload(url):
        seen["url"] = url
        return [
            {"title": "no url"},
            {"url": "https://dev.to/x"},
            {
                "title": "ok",
                "url": "https://dev.to/ok",
                "public_reactions_count": 10,
                "comments_count": 2,
                "published_at": "2026-04-26T12:00:00Z",
                "user": {"name": "Ann"},
                "description": "desc",
            },
        ]

    monkeypatch.setattr(research, "_http_get_json", payload)
    out = research.fetch_devto("Machine Learning")
    assert [s.title for s in out] == ["ok"]
    assert out[0].author == "Ann"
    assert out[0].extra["tag"] == "machine-learning"
    assert "tag=machine-learning" in seen["url"]


def test_hn_falls_back_to_item_url_and_skips_untitled(monkeypatch):
    monkeypatch.setattr(
        research,
        "_http_get_json",
        lambda url: {
            "hits": [
                {"objectID": "1"},  # no title
                {"story_title": "Ask HN", "objectID": "42", "points": 5},
            ]
        },
    )
    out = research.fetch_hn("q")
    assert len(out) == 1
    assert out[0].url == "https://news.ycombinator.com/item?id=42"


def test_reddit_skips_children_without_title_or_permalink(monkeypatch):
    monkeypatch.setattr(
        research,
        "_http_get_json",
        lambda url: {"data": {"children": [{"data": {"title": "t"}}, {"data": {"permalink": "/r/x"}}, {}]}},
    )
    assert research.fetch_reddit("q") == []
    monkeypatch.setattr(research, "_http_get_json", lambda url: {})
    assert research.fetch_reddit("q") == []


# --- run_research orchestration ---------------------------------------------


def test_run_research_no_jobs_returns_empty():
    assert research.run_research(ResearchRequest(queries=[], rss_feeds=[])) == []
    assert research.run_research(ResearchRequest(queries=["  "], sources=["hn"])) == []
    assert research.run_research(ResearchRequest(queries=["q"], sources=["unknown"])) == []


def test_run_research_sorts_dedupes_and_survives_raising_source(monkeypatch):
    fetchers = {
        "hn": lambda q, n: [
            Snippet(source="hn", url="https://dup", title="dup-low", score=0.1),
            Snippet(source="hn", url="https://a", title="a", score=0.5),
        ],
        "devto": lambda q, n: [Snippet(source="devto", url="https://dup", title="dup-high", score=0.9)],
        "reddit": _raise(RuntimeError("boom")),
        "rss": lambda q, n: [Snippet(source="rss", url=f"{q}#1", title="r", score=0.3)],
    }
    monkeypatch.setattr(research, "SOURCE_FETCHERS", fetchers)
    out = research.run_research(ResearchRequest(queries=["q"], rss_feeds=["https://feed"]))
    assert [s.title for s in out] == ["dup-high", "a", "r"]


# --- helpers -----------------------------------------------------------------


def test_parse_iso_variants():
    assert research._parse_iso(None) is None
    assert research._parse_iso("2026-04-26T12:00:00Z") == datetime(2026, 4, 26, 12, tzinfo=timezone.utc)
    rfc = research._parse_iso("Sun, 26 Apr 2026 12:00:00 +0000")
    assert rfc == datetime(2026, 4, 26, 12, tzinfo=timezone.utc)
    assert research._parse_iso("not a date") is None


def test_from_unix():
    assert research._from_unix(None) is None
    assert research._from_unix("nope") is None
    assert research._from_unix(0) == datetime(1970, 1, 1, tzinfo=timezone.utc)


def test_recency_factor():
    now = datetime(2026, 1, 3, tzinfo=timezone.utc)
    assert research._recency_factor(None) == 0.5
    assert research._recency_factor(now, now=now) == 1.0
    two_days = now - timedelta(hours=research.RECENCY_HALF_LIFE_HOURS)
    assert research._recency_factor(two_days, now=now) == pytest.approx(0.5)
    # Naive datetimes are treated as UTC; future dates clamp to 1.0.
    assert research._recency_factor(two_days.replace(tzinfo=None), now=now) == pytest.approx(0.5)
    assert research._recency_factor(now + timedelta(hours=5), now=now) == 1.0


def test_normalize_and_compose_score():
    assert research._normalize(0, soft_max=10) == 0.0
    assert research._normalize(-5, soft_max=10) == 0.0
    assert 0.6 < research._normalize(10, soft_max=10) < 0.7
    assert research._compose_score(0, soft_max=10, published_at=None) == 0.0


def test_format_for_prompt_truncates_long_snippets_and_caps_total():
    long = Snippet(source="hn", url="https://u", title="T", snippet="x\n" * 200)
    text = research.format_for_prompt([long])
    assert text.startswith("- [hn] T (https://u)")
    assert text.endswith("...")
    assert "\n    " in text

    many = [Snippet(source="hn", url=f"https://u/{i}", title="t" * 50) for i in range(100)]
    capped = research.format_for_prompt(many, max_chars=300)
    assert capped.count("- [hn]") < 100


def test_snippet_to_dict_serialises_datetime():
    s = Snippet(source="rss", url="u", title="t", published_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert s.to_dict()["published_at"] == "2026-01-01T00:00:00+00:00"
    assert Snippet(source="rss", url="u", title="t").to_dict()["published_at"] is None


def test_rss_atom_with_text_link_and_updated_fallback(monkeypatch):
    xml = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom entry</title>
    <link>https://atom/1</link>
    <content>body text</content>
    <updated>2026-04-26T12:00:00Z</updated>
  </entry>
</feed>"""
    monkeypatch.setattr(research, "_http_get", lambda url, timeout=5.0: xml)
    out = research.fetch_rss("https://f/atom")
    assert len(out) == 1
    assert out[0].url == "https://atom/1"
    assert out[0].snippet == "body text"
    assert out[0].author is None
    assert out[0].published_at == datetime(2026, 4, 26, 12, tzinfo=timezone.utc)
