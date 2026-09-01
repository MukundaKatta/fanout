"""Stdlib-``unittest`` tests for the research module's source fetchers.

Every real network call funnels through ``research._http_get`` /
``research._http_get_json``, so we patch those two functions with
``unittest.mock.patch`` and never touch the network. This mirrors the intent
of the original pytest suite but runs with only the standard library.

Run with::

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import logging
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import tests._path  # noqa: F401  (side effect: puts backend/ on sys.path)

from app import research  # noqa: E402

# Error-path tests deliberately trigger ``log.warning`` calls (a flaky source
# must degrade silently rather than crash the run). Silence them so the test
# runner output stays clean — the assertions, not the log lines, prove the
# behaviour.
logging.getLogger("app.research").setLevel(logging.ERROR)
from app.research import (  # noqa: E402
    ResearchRequest,
    Snippet,
    fetch_devto,
    fetch_hn,
    fetch_reddit,
    fetch_rss,
    run_research,
)


def _iso(hours_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class FetchHnTests(unittest.TestCase):
    def test_parses_hits_and_drops_titleless(self) -> None:
        payload = {
            "hits": [
                {
                    "title": "Show HN: A neat thing",
                    "url": "https://example.com/a",
                    "author": "alice",
                    "points": 120,
                    "num_comments": 30,
                    "created_at": _iso(4),
                    "objectID": "1",
                },
                {
                    "story_title": "Ask HN: Question",  # no url -> item fallback
                    "objectID": "2",
                    "points": 0,
                    "num_comments": 0,
                    "created_at": _iso(28),
                },
                {"objectID": "3"},  # no title -> dropped
            ]
        }
        with mock.patch.object(research, "_http_get_json", return_value=payload):
            out = fetch_hn("agents")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].url, "https://example.com/a")
        self.assertEqual(out[0].source, "hn")
        self.assertGreater(out[0].score, 0)
        self.assertLessEqual(out[0].score, 1)
        self.assertEqual(out[1].url, "https://news.ycombinator.com/item?id=2")

    def test_empty_query_skips_network(self) -> None:
        with mock.patch.object(research, "_http_get_json", side_effect=AssertionError):
            self.assertEqual(fetch_hn("   "), [])

    def test_network_error_degrades_to_empty_list(self) -> None:
        with mock.patch.object(research, "_http_get_json", side_effect=OSError("down")):
            self.assertEqual(fetch_hn("agents"), [])


class FetchDevtoTests(unittest.TestCase):
    def test_tag_is_normalised_and_invalid_rows_dropped(self) -> None:
        captured = {}

        def fake(url, timeout=5.0):
            captured["url"] = url
            return [
                {
                    "title": "Building agents",
                    "url": "https://dev.to/x/agents",
                    "description": "summary",
                    "public_reactions_count": 50,
                    "comments_count": 10,
                    "published_at": _iso(8),
                    "user": {"name": "Bob"},
                },
                {"title": "no url"},  # dropped
            ]

        with mock.patch.object(research, "_http_get_json", side_effect=fake):
            out = fetch_devto("AI Agents")  # space + caps -> "ai-agents"
        self.assertIn("tag=ai-agents", captured["url"])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].author, "Bob")

    def test_punctuation_only_tag_skips_network(self) -> None:
        with mock.patch.object(research, "_http_get_json", side_effect=AssertionError):
            self.assertEqual(fetch_devto("!!!"), [])

    def test_non_list_payload_returns_empty(self) -> None:
        with mock.patch.object(research, "_http_get_json", return_value={"error": "x"}):
            self.assertEqual(fetch_devto("python"), [])


class FetchRedditTests(unittest.TestCase):
    def test_parses_children(self) -> None:
        payload = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "AI agents are hot",
                            "permalink": "/r/foo/comments/abc/",
                            "selftext": "discussion",
                            "ups": 200,
                            "num_comments": 80,
                            "created_utc": (
                                datetime.now(timezone.utc) - timedelta(hours=4)
                            ).timestamp(),
                            "author": "u1",
                            "subreddit": "foo",
                        }
                    },
                    {"data": {"title": "no permalink"}},  # dropped
                ]
            }
        }
        with mock.patch.object(research, "_http_get_json", return_value=payload):
            out = fetch_reddit("agents")
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].url.startswith("https://www.reddit.com/r/foo/comments/"))
        self.assertEqual(out[0].extra["subreddit"], "foo")
        self.assertGreater(out[0].score, 0)

    def test_empty_query_skips_network(self) -> None:
        with mock.patch.object(research, "_http_get_json", side_effect=AssertionError):
            self.assertEqual(fetch_reddit(""), [])


class FetchRssTests(unittest.TestCase):
    def test_rss20_shape(self) -> None:
        pubdate = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime(
            "%a, %d %b %Y %H:%M:%S +0000"
        )
        body = (
            '<?xml version="1.0"?><rss><channel>'
            f"<item><title>Item A</title><link>https://a.example</link>"
            f"<description>desc</description><pubDate>{pubdate}</pubDate></item>"
            "<item><title>No link</title></item>"
            "</channel></rss>"
        ).encode()
        with mock.patch.object(research, "_http_get", return_value=body):
            out = fetch_rss("https://blog.example/feed.xml")
        self.assertEqual([s.title for s in out], ["Item A"])
        self.assertGreater(out[0].score, 0)

    def test_atom_shape(self) -> None:
        updated = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        body = (
            '<?xml version="1.0"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            "<title>Atom A</title><link href=\"https://a.atom\"/>"
            f"<summary>summary</summary><updated>{updated}</updated>"
            "<author><name>Bob</name></author></entry></feed>"
        ).encode()
        with mock.patch.object(research, "_http_get", return_value=body):
            out = fetch_rss("https://blog.example/atom.xml")
        self.assertEqual([s.title for s in out], ["Atom A"])
        self.assertEqual(out[0].author, "Bob")
        self.assertEqual(out[0].url, "https://a.atom")

    def test_bad_xml_returns_empty(self) -> None:
        with mock.patch.object(research, "_http_get", return_value=b"<not-valid>"):
            self.assertEqual(fetch_rss("https://blog.example/feed.xml"), [])

    def test_network_error_returns_empty(self) -> None:
        with mock.patch.object(research, "_http_get", side_effect=OSError("down")):
            self.assertEqual(fetch_rss("https://blog.example/feed.xml"), [])


class RunResearchTests(unittest.TestCase):
    def _patch_fetchers(self, **overrides):
        base = {
            "hn": lambda q, n: [],
            "devto": lambda q, n: [],
            "reddit": lambda q, n: [],
            "rss": lambda q, n: [],
        }
        base.update(overrides)
        return mock.patch.dict(research.SOURCE_FETCHERS, base, clear=True)

    def test_dedupes_by_url_keeping_highest_score(self) -> None:
        shared = "https://example.com/x"
        with self._patch_fetchers(
            hn=lambda q, n: [Snippet(source="hn", url=shared, title="HN", score=0.4)],
            reddit=lambda q, n: [
                Snippet(source="reddit", url=shared, title="Reddit", score=0.8)
            ],
        ):
            result = run_research(
                ResearchRequest(queries=["agents"], sources=["hn", "reddit", "devto"])
            )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source, "reddit")
        self.assertEqual(result[0].score, 0.8)

    def test_results_are_sorted_by_score_desc(self) -> None:
        with self._patch_fetchers(
            hn=lambda q, n: [
                Snippet(source="hn", url="https://low", title="low", score=0.2),
                Snippet(source="hn", url="https://high", title="high", score=0.9),
            ],
        ):
            result = run_research(ResearchRequest(queries=["x"], sources=["hn"]))
        self.assertEqual([s.score for s in result], [0.9, 0.2])

    def test_one_source_failure_does_not_crash_run(self) -> None:
        def bad(q, n):
            raise RuntimeError("boom")

        with self._patch_fetchers(
            hn=lambda q, n: [Snippet(source="hn", url="https://ok", title="ok", score=0.5)],
            reddit=bad,
        ):
            result = run_research(
                ResearchRequest(queries=["agents"], sources=["hn", "reddit"])
            )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].url, "https://ok")

    def test_no_jobs_returns_empty(self) -> None:
        self.assertEqual(run_research(ResearchRequest(queries=[], rss_feeds=[])), [])

    def test_blank_queries_produce_no_jobs(self) -> None:
        with self._patch_fetchers(
            hn=lambda q, n: [Snippet(source="hn", url="https://x", title="t", score=1.0)],
        ):
            result = run_research(ResearchRequest(queries=["   ", ""], sources=["hn"]))
        self.assertEqual(result, [])

    def test_rss_feeds_drive_rss_source_only(self) -> None:
        captured = []

        def rss(feed, n):
            captured.append(feed)
            return [Snippet(source="rss", url=feed, title="t", score=0.3)]

        with self._patch_fetchers(rss=rss):
            result = run_research(
                ResearchRequest(
                    queries=[],
                    rss_feeds=["https://a/feed", "https://b/feed"],
                    sources=["rss"],
                )
            )
        self.assertEqual(sorted(captured), ["https://a/feed", "https://b/feed"])
        self.assertEqual(len(result), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
