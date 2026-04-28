"""Tests for the research module.

Network is mocked at the ``_http_get`` / ``_http_get_json`` boundary — every
real HTTP call funnels through those two functions, so monkeypatching them is
sufficient and we never touch the network in tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import research
from app.research import (
    ResearchRequest,
    Snippet,
    fetch_devto,
    fetch_hn,
    fetch_reddit,
    fetch_rss,
    format_for_prompt,
    run_research,
)


# ---------------------------------------------------------------------------
# Per-source unit tests
# ---------------------------------------------------------------------------


def test_fetch_hn_parses_hits(monkeypatch):
    payload = {
        "hits": [
            {
                "title": "Show HN: A neat thing",
                "url": "https://example.com/a",
                "author": "alice",
                "points": 120,
                "num_comments": 30,
                "created_at": "2026-04-26T08:00:00Z",
                "objectID": "1",
            },
            {
                # no url → falls back to HN item link
                "story_title": "Ask HN: Question",
                "objectID": "2",
                "points": 0,
                "num_comments": 0,
                "created_at": "2026-04-25T08:00:00Z",
            },
            {"objectID": "3"},  # missing title — must be dropped
        ]
    }
    monkeypatch.setattr(research, "_http_get_json", lambda *a, **kw: payload)
    out = fetch_hn("agents")
    assert len(out) == 2
    assert out[0].title == "Show HN: A neat thing"
    assert out[0].url == "https://example.com/a"
    assert out[0].source == "hn"
    assert 0 < out[0].score <= 1
    # Fallback URL form for the second hit:
    assert out[1].url == "https://news.ycombinator.com/item?id=2"


def test_fetch_hn_empty_query_skips_network(monkeypatch):
    called = False

    def boom(*a, **kw):
        nonlocal called
        called = True
        raise AssertionError("should not be called")

    monkeypatch.setattr(research, "_http_get_json", boom)
    assert fetch_hn("   ") == []
    assert not called


def test_fetch_hn_swallows_network_errors(monkeypatch):
    def boom(*a, **kw):
        raise OSError("network down")

    monkeypatch.setattr(research, "_http_get_json", boom)
    # Errors must degrade silently — one bad source should never crash a research run.
    assert fetch_hn("agents") == []


def test_fetch_devto_normalises_tag_and_drops_invalid(monkeypatch):
    seen: dict = {}

    def fake(url, timeout=5.0):
        seen["url"] = url
        return [
            {
                "title": "Building agents",
                "url": "https://dev.to/x/agents",
                "description": "summary",
                "public_reactions_count": 50,
                "comments_count": 10,
                "published_at": "2026-04-25T00:00:00Z",
                "user": {"name": "Bob"},
            },
            {"title": "no url"},  # missing url → dropped
        ]

    monkeypatch.setattr(research, "_http_get_json", fake)
    out = fetch_devto("AI Agents")  # space + caps → must become "ai-agents"
    assert "tag=ai-agents" in seen["url"]
    assert len(out) == 1
    assert out[0].author == "Bob"


def test_fetch_devto_empty_tag(monkeypatch):
    monkeypatch.setattr(research, "_http_get_json", lambda *a, **kw: [])
    assert fetch_devto("!!!") == []  # nothing alphanumeric → no fetch needed


def test_fetch_reddit_parses_children(monkeypatch):
    monkeypatch.setattr(
        research,
        "_http_get_json",
        lambda *a, **kw: {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "AI agents are hot",
                            "permalink": "/r/foo/comments/abc/",
                            "selftext": "discussion",
                            "ups": 200,
                            "num_comments": 80,
                            "created_utc": (datetime.now(timezone.utc) - timedelta(hours=4)).timestamp(),
                            "author": "u1",
                            "subreddit": "foo",
                        }
                    },
                    {"data": {"title": "no permalink"}},  # dropped
                ]
            }
        },
    )
    out = fetch_reddit("agents")
    assert len(out) == 1
    assert out[0].url.startswith("https://www.reddit.com/r/foo/comments/")
    assert out[0].extra["subreddit"] == "foo"
    assert out[0].score > 0


def test_fetch_rss_atom_and_rss20(monkeypatch):
    rss20 = b"""<?xml version="1.0"?>
<rss><channel>
  <item><title>Item A</title><link>https://a.example</link>
    <description>desc</description><pubDate>Sun, 26 Apr 2026 12:00:00 +0000</pubDate>
  </item>
  <item><title>No link</title></item>
</channel></rss>"""

    monkeypatch.setattr(research, "_http_get", lambda *a, **kw: rss20)
    out = fetch_rss("https://blog.example/feed.xml")
    assert [s.title for s in out] == ["Item A"]
    assert out[0].score > 0  # recency-only score, but non-zero

    atom = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom A</title>
    <link href="https://a.atom"/>
    <summary>summary</summary>
    <updated>2026-04-26T12:00:00Z</updated>
    <author><name>Bob</name></author>
  </entry>
</feed>"""
    monkeypatch.setattr(research, "_http_get", lambda *a, **kw: atom)
    out = fetch_rss("https://blog.example/atom.xml")
    assert [s.title for s in out] == ["Atom A"]
    assert out[0].author == "Bob"
    assert out[0].url == "https://a.atom"


def test_fetch_rss_bad_xml_returns_empty(monkeypatch):
    monkeypatch.setattr(research, "_http_get", lambda *a, **kw: b"<not-valid>")
    assert fetch_rss("https://blog.example/feed.xml") == []


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_recency_factor_decay():
    now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    # Brand-new content scores ~1
    assert research._recency_factor(now, now=now) == pytest.approx(1.0, abs=1e-3)
    # 48h-old content (= half-life) scores ~0.5
    assert research._recency_factor(now - timedelta(hours=48), now=now) == pytest.approx(0.5, abs=1e-3)
    # Unknown timestamp → neutral 0.5 (not zero — we don't punish opaque sources)
    assert research._recency_factor(None) == 0.5


def test_compose_score_bounds():
    now = datetime.now(timezone.utc)
    s_zero = research._compose_score(0, soft_max=100, published_at=now)
    s_big = research._compose_score(10_000, soft_max=100, published_at=now)
    assert s_zero == 0.0
    assert 0.9 <= s_big <= 1.0


# ---------------------------------------------------------------------------
# run_research — orchestration + dedup
# ---------------------------------------------------------------------------


def test_run_research_dedupes_by_url(monkeypatch):
    # Both HN and Reddit return the same URL → only one entry in the output.
    shared = "https://example.com/x"

    def fake_hn(q, limit):
        return [Snippet(source="hn", url=shared, title="HN copy", score=0.4)]

    def fake_reddit(q, limit):
        return [Snippet(source="reddit", url=shared, title="Reddit copy", score=0.8)]

    monkeypatch.setitem(research.SOURCE_FETCHERS, "hn", fake_hn)
    monkeypatch.setitem(research.SOURCE_FETCHERS, "reddit", fake_reddit)
    monkeypatch.setitem(research.SOURCE_FETCHERS, "devto", lambda *a, **kw: [])
    monkeypatch.setitem(research.SOURCE_FETCHERS, "rss", lambda *a, **kw: [])

    result = run_research(
        ResearchRequest(queries=["agents"], sources=["hn", "reddit", "devto"])
    )
    assert len(result) == 1
    # Highest-scoring duplicate wins — Reddit (0.8) here.
    assert result[0].score == 0.8
    assert result[0].source == "reddit"


def test_run_research_one_source_failure_doesnt_crash(monkeypatch):
    def good(q, limit):
        return [Snippet(source="hn", url="https://ok.example", title="ok", score=0.5)]

    def bad(q, limit):
        raise RuntimeError("boom")

    monkeypatch.setitem(research.SOURCE_FETCHERS, "hn", good)
    monkeypatch.setitem(research.SOURCE_FETCHERS, "reddit", bad)
    monkeypatch.setitem(research.SOURCE_FETCHERS, "devto", lambda *a, **kw: [])
    monkeypatch.setitem(research.SOURCE_FETCHERS, "rss", lambda *a, **kw: [])

    result = run_research(
        ResearchRequest(queries=["agents"], sources=["hn", "reddit", "devto"])
    )
    assert len(result) == 1
    assert result[0].url == "https://ok.example"


def test_run_research_no_jobs_returns_empty():
    assert run_research(ResearchRequest(queries=[], rss_feeds=[])) == []


# ---------------------------------------------------------------------------
# format_for_prompt — caps total length
# ---------------------------------------------------------------------------


def test_format_for_prompt_truncates():
    snippets = [
        Snippet(source="hn", url=f"https://e.com/{i}", title=f"t{i}", snippet="x" * 500)
        for i in range(20)
    ]
    out = format_for_prompt(snippets, max_chars=500)
    assert len(out) <= 700  # max_chars + tail of last line
    assert out.startswith("- [hn]")
