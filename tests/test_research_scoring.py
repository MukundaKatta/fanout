"""Stdlib-``unittest`` tests for the research module's pure logic.

Scoring, normalisation, recency decay, dedup and prompt formatting are all
pure functions with no I/O, so they are the highest-value things to lock down
with a dependency-free suite. Run with::

    python3 -m unittest discover -s tests

The complementary network-boundary tests live in ``test_research_sources.py``;
the original pytest suite under ``backend/tests/`` overlaps in spirit but
requires the full dependency stack to be installed.
"""

from __future__ import annotations

import math
import unittest
from datetime import datetime, timedelta, timezone

import tests._path  # noqa: F401  (side effect: puts backend/ on sys.path)

from app import research  # noqa: E402
from app.research import Snippet, format_for_prompt  # noqa: E402


class RecencyFactorTests(unittest.TestCase):
    def test_brand_new_content_scores_near_one(self) -> None:
        now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
        self.assertAlmostEqual(research._recency_factor(now, now=now), 1.0, places=3)

    def test_half_life_content_scores_near_half(self) -> None:
        now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
        half = now - timedelta(hours=research.RECENCY_HALF_LIFE_HOURS)
        self.assertAlmostEqual(research._recency_factor(half, now=now), 0.5, places=3)

    def test_two_half_lives_scores_near_quarter(self) -> None:
        now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
        old = now - timedelta(hours=2 * research.RECENCY_HALF_LIFE_HOURS)
        self.assertAlmostEqual(research._recency_factor(old, now=now), 0.25, places=3)

    def test_unknown_timestamp_is_neutral(self) -> None:
        # Opaque sources get a neutral 0.5 rather than a zero penalty.
        self.assertEqual(research._recency_factor(None), 0.5)

    def test_naive_datetime_is_treated_as_utc(self) -> None:
        now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
        naive = datetime(2026, 4, 26, 12, 0)  # no tzinfo
        self.assertAlmostEqual(research._recency_factor(naive, now=now), 1.0, places=3)

    def test_future_timestamp_is_clamped_not_amplified(self) -> None:
        # A clock-skewed "future" item must not score above a brand-new one.
        now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
        future = now + timedelta(hours=10)
        self.assertAlmostEqual(research._recency_factor(future, now=now), 1.0, places=6)


class NormalizeTests(unittest.TestCase):
    def test_zero_and_negative_clamp_to_zero(self) -> None:
        self.assertEqual(research._normalize(0, soft_max=100), 0.0)
        self.assertEqual(research._normalize(-50, soft_max=100), 0.0)

    def test_output_is_bounded_to_unit_interval(self) -> None:
        # Output saturates at 1.0 for very large values (exp underflow), so the
        # closed interval [0, 1] is the contract, not the half-open [0, 1).
        for value in (1, 50, 200, 10_000):
            out = research._normalize(value, soft_max=100)
            self.assertGreaterEqual(out, 0.0)
            self.assertLessEqual(out, 1.0)

    def test_monotonic_increasing(self) -> None:
        small = research._normalize(10, soft_max=100)
        big = research._normalize(500, soft_max=100)
        self.assertLess(small, big)

    def test_soft_max_curve_shape(self) -> None:
        # At value == soft_max the curve is 1 - e^-1 ~= 0.632.
        out = research._normalize(100, soft_max=100)
        self.assertAlmostEqual(out, 1.0 - math.exp(-1), places=6)


class ComposeScoreTests(unittest.TestCase):
    def test_zero_popularity_scores_zero(self) -> None:
        now = datetime.now(timezone.utc)
        self.assertEqual(research._compose_score(0, soft_max=100, published_at=now), 0.0)

    def test_high_popularity_fresh_scores_near_one(self) -> None:
        now = datetime.now(timezone.utc)
        out = research._compose_score(10_000, soft_max=100, published_at=now)
        self.assertGreaterEqual(out, 0.9)
        self.assertLessEqual(out, 1.0)

    def test_geometric_mean_punishes_a_weak_factor(self) -> None:
        # Popular but stale should score well below popular and fresh because
        # the score is the geometric mean of popularity and recency.
        now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
        fresh = research._compose_score(10_000, soft_max=100, published_at=now)
        stale = research._compose_score(
            10_000,
            soft_max=100,
            published_at=now - timedelta(hours=10 * research.RECENCY_HALF_LIFE_HOURS),
        )
        self.assertLess(stale, fresh)

    def test_score_is_rounded_to_four_places(self) -> None:
        now = datetime.now(timezone.utc)
        out = research._compose_score(123, soft_max=100, published_at=now)
        self.assertEqual(out, round(out, 4))


class DedupeTests(unittest.TestCase):
    def test_keeps_first_occurrence_of_a_url(self) -> None:
        a = Snippet(source="hn", url="https://dup", title="first", score=0.9)
        b = Snippet(source="reddit", url="https://dup", title="second", score=0.1)
        c = Snippet(source="devto", url="https://unique", title="third", score=0.5)
        out = research._dedupe_by_url([a, b, c])
        self.assertEqual([s.title for s in out], ["first", "third"])

    def test_empty_input(self) -> None:
        self.assertEqual(research._dedupe_by_url([]), [])


class ParseIsoTests(unittest.TestCase):
    def test_trailing_z_is_handled(self) -> None:
        dt = research._parse_iso("2026-04-26T12:00:00Z")
        self.assertIsNotNone(dt)
        assert dt is not None  # for type-checkers
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.year, 2026)

    def test_offset_form_is_handled(self) -> None:
        dt = research._parse_iso("2026-04-26T12:00:00+00:00")
        self.assertIsNotNone(dt)

    def test_rfc822_pubdate_fallback(self) -> None:
        # RSS <pubDate> uses RFC-822; fromisoformat rejects it, the email-utils
        # fallback must catch it.
        dt = research._parse_iso("Sun, 26 Apr 2026 12:00:00 +0000")
        self.assertIsNotNone(dt)
        assert dt is not None
        self.assertEqual(dt.year, 2026)

    def test_none_and_garbage_return_none(self) -> None:
        self.assertIsNone(research._parse_iso(None))
        self.assertIsNone(research._parse_iso(""))
        self.assertIsNone(research._parse_iso("not a date at all"))


class FromUnixTests(unittest.TestCase):
    def test_valid_epoch_seconds(self) -> None:
        dt = research._from_unix(1_700_000_000)
        self.assertIsNotNone(dt)
        assert dt is not None
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_string_seconds_are_coerced(self) -> None:
        self.assertIsNotNone(research._from_unix("1700000000"))

    def test_none_and_garbage_return_none(self) -> None:
        self.assertIsNone(research._from_unix(None))
        self.assertIsNone(research._from_unix("not-a-number"))


class SnippetTests(unittest.TestCase):
    def test_to_dict_serialises_datetime_to_iso(self) -> None:
        published = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
        s = Snippet(source="hn", url="https://x", title="t", published_at=published)
        d = s.to_dict()
        self.assertEqual(d["published_at"], published.isoformat())
        self.assertEqual(d["source"], "hn")

    def test_to_dict_handles_none_datetime(self) -> None:
        s = Snippet(source="hn", url="https://x", title="t")
        self.assertIsNone(s.to_dict()["published_at"])

    def test_extra_defaults_to_independent_dict(self) -> None:
        a = Snippet(source="hn", url="https://a", title="a")
        b = Snippet(source="hn", url="https://b", title="b")
        a.extra["k"] = "v"
        # The dataclass default_factory must not share one dict across instances.
        self.assertEqual(b.extra, {})


class FormatForPromptTests(unittest.TestCase):
    def test_empty_input_returns_empty_string(self) -> None:
        self.assertEqual(format_for_prompt([]), "")

    def test_renders_source_and_url(self) -> None:
        s = Snippet(source="hn", url="https://x", title="Title")
        out = format_for_prompt([s])
        self.assertIn("[hn]", out)
        self.assertIn("Title", out)
        self.assertIn("https://x", out)

    def test_long_snippet_text_is_truncated_with_ellipsis(self) -> None:
        s = Snippet(source="hn", url="https://x", title="t", snippet="y" * 500)
        out = format_for_prompt([s])
        self.assertIn("...", out)

    def test_respects_max_chars_budget(self) -> None:
        snippets = [
            Snippet(source="hn", url=f"https://e/{i}", title=f"t{i}", snippet="x" * 400)
            for i in range(50)
        ]
        out = format_for_prompt(snippets, max_chars=500)
        # The loop appends-then-checks, so the cap is max_chars + the tail of
        # one last line; assert it didn't run away to thousands of chars.
        self.assertLessEqual(len(out), 900)
        self.assertTrue(out.startswith("- [hn]"))

    def test_snippetless_entries_render_single_line(self) -> None:
        s = Snippet(source="rss", url="https://x", title="t")  # no snippet text
        out = format_for_prompt([s])
        self.assertEqual(out.count("\n"), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
