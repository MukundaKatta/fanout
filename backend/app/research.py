"""Research loop — pull live signals to feed the agent's planning step.

Why this exists
---------------
The agent without research only knows what the user typed in the product blurb.
On X/HN/Reddit, posts that reference the conversation already happening get
traction; posts that don't get ignored. The research loop pulls *current*
signals (top HN stories, Dev.to articles, Reddit threads, RSS feeds) so drafts
can cite what's actually being discussed right now.

Sources are intentionally **free + keyless** to match Fanout's "no third-party
API keys to authorise" ethos:

- HN Algolia search       https://hn.algolia.com/api  (search by query)
- Dev.to public articles  https://dev.to/api/articles (filter by tag)
- Reddit public JSON      https://www.reddit.com/search.json
- RSS / Atom feeds        any URL the user provides

Each source returns a list of ``Snippet``. The caller (store + agent) is
responsible for persistence and dedup.
"""

from __future__ import annotations

import json
import logging
import math
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Iterable

log = logging.getLogger(__name__)

USER_AGENT = "fanout-research/0.1 (+https://github.com/MukundaKatta/fanout)"
DEFAULT_TIMEOUT = 5.0  # seconds — keep the loop snappy; one slow source mustn't stall a run.
PER_SOURCE_LIMIT = 10
RECENCY_HALF_LIFE_HOURS = 48.0  # popularity halves every 2 days


# ---------------------------------------------------------------------------
# Snippet — the unit of research returned by every source.
# ---------------------------------------------------------------------------


@dataclass
class Snippet:
    source: str  # "hn" | "devto" | "reddit" | "rss"
    url: str
    title: str
    snippet: str | None = None
    author: str | None = None
    score: float = 0.0  # 0..1, computed after fetch (popularity * recency)
    published_at: datetime | None = None
    query: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_at"] = self.published_at.isoformat() if self.published_at else None
        return d


# ---------------------------------------------------------------------------
# HTTP — stdlib only, so unit tests can monkeypatch ``_http_get`` cleanly
# without dragging in ``requests`` or ``httpx``. The whole network surface
# of this module funnels through this one function.
# ---------------------------------------------------------------------------


def _http_get(url: str, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URLs are validated upstream)
        return resp.read()


def _http_get_json(url: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
    body = _http_get(url, timeout=timeout)
    return json.loads(body.decode("utf-8"))


# ---------------------------------------------------------------------------
# Scoring — blend upstream popularity with recency so the signal mix favours
# items that are *both* discussed and fresh. Recency uses an exponential
# half-life so 2-day-old content is worth half what brand-new content is.
# ---------------------------------------------------------------------------


def _recency_factor(published_at: datetime | None, *, now: datetime | None = None) -> float:
    if published_at is None:
        return 0.5  # unknown age — neutral
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
    return 0.5 ** (hours / RECENCY_HALF_LIFE_HOURS)


def _normalize(value: float, *, soft_max: float) -> float:
    """Squash a raw popularity number to [0, 1] using a soft saturation curve.

    ``soft_max`` is the value at which we want the output to be ~0.7 — past
    that point we compress aggressively so a viral post (10k upvotes) doesn't
    drown out genuinely-relevant smaller posts.
    """
    if value <= 0:
        return 0.0
    return 1.0 - math.exp(-value / soft_max)


def _compose_score(popularity: float, *, soft_max: float, published_at: datetime | None) -> float:
    pop = _normalize(popularity, soft_max=soft_max)
    rec = _recency_factor(published_at)
    # Geometric mean — both factors must be reasonable to score well.
    return round((pop * rec) ** 0.5, 4)


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def fetch_hn(query: str, *, limit: int = PER_SOURCE_LIMIT) -> list[Snippet]:
    """Hacker News via Algolia.

    Sorts by relevance to ``query`` and trims to ``limit``. We score against
    upstream points (soft-max 200 ≈ a respectable HN front-page item).
    """
    if not query.strip():
        return []
    qs = urllib.parse.urlencode({"query": query, "tags": "story", "hitsPerPage": limit})
    url = f"https://hn.algolia.com/api/v1/search?{qs}"
    try:
        data = _http_get_json(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        log.warning("hn fetch failed: %s", e)
        return []

    out: list[Snippet] = []
    for hit in data.get("hits", []):
        title = hit.get("title") or hit.get("story_title")
        if not title:
            continue
        story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        published_at = _parse_iso(hit.get("created_at"))
        points = float(hit.get("points") or 0)
        comments = float(hit.get("num_comments") or 0)
        # Comments are a stronger discussion signal than raw points — weight them slightly higher.
        popularity = points + 1.5 * comments
        out.append(
            Snippet(
                source="hn",
                url=story_url,
                title=title,
                author=hit.get("author"),
                published_at=published_at,
                score=_compose_score(popularity, soft_max=200, published_at=published_at),
                query=query,
                extra={"points": points, "comments": comments, "object_id": hit.get("objectID")},
            )
        )
    return out


def fetch_devto(tag: str, *, limit: int = PER_SOURCE_LIMIT) -> list[Snippet]:
    """Dev.to public articles for a tag.

    Dev.to's free endpoint takes a single tag (e.g. ``ai``, ``python``).
    Multi-word queries are sanitised to lowercase + dashes.
    """
    norm_tag = "".join(c if c.isalnum() else "-" for c in tag.lower()).strip("-")
    if not norm_tag:
        return []
    qs = urllib.parse.urlencode({"tag": norm_tag, "per_page": limit, "top": 7})
    url = f"https://dev.to/api/articles?{qs}"
    try:
        data = _http_get_json(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        log.warning("devto fetch failed: %s", e)
        return []

    if not isinstance(data, list):
        return []
    out: list[Snippet] = []
    for art in data[:limit]:
        title = art.get("title")
        article_url = art.get("url")
        if not title or not article_url:
            continue
        reactions = float(art.get("public_reactions_count") or 0)
        comments = float(art.get("comments_count") or 0)
        popularity = reactions + 1.5 * comments
        published_at = _parse_iso(art.get("published_at"))
        out.append(
            Snippet(
                source="devto",
                url=article_url,
                title=title,
                snippet=art.get("description"),
                author=(art.get("user") or {}).get("name"),
                published_at=published_at,
                score=_compose_score(popularity, soft_max=120, published_at=published_at),
                query=tag,
                extra={"reactions": reactions, "comments": comments, "tag": norm_tag},
            )
        )
    return out


def fetch_reddit(query: str, *, limit: int = PER_SOURCE_LIMIT) -> list[Snippet]:
    """Reddit public search JSON.

    Reddit rate-limits unauthed requests; the configured User-Agent helps
    avoid 429s. We score against upvotes + comments (soft-max 500).
    """
    if not query.strip():
        return []
    qs = urllib.parse.urlencode({"q": query, "limit": limit, "sort": "hot", "t": "week"})
    url = f"https://www.reddit.com/search.json?{qs}"
    try:
        data = _http_get_json(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        log.warning("reddit fetch failed: %s", e)
        return []

    out: list[Snippet] = []
    for child in (data.get("data") or {}).get("children", []):
        d = child.get("data") or {}
        title = d.get("title")
        permalink = d.get("permalink")
        if not title or not permalink:
            continue
        post_url = f"https://www.reddit.com{permalink}"
        ups = float(d.get("ups") or 0)
        comments = float(d.get("num_comments") or 0)
        popularity = ups + 1.5 * comments
        # Reddit gives unix seconds in created_utc.
        published_at = _from_unix(d.get("created_utc"))
        out.append(
            Snippet(
                source="reddit",
                url=post_url,
                title=title,
                snippet=d.get("selftext") or None,
                author=d.get("author"),
                published_at=published_at,
                score=_compose_score(popularity, soft_max=500, published_at=published_at),
                query=query,
                extra={"ups": ups, "comments": comments, "subreddit": d.get("subreddit")},
            )
        )
    return out


def fetch_rss(feed_url: str, *, limit: int = PER_SOURCE_LIMIT) -> list[Snippet]:
    """RSS / Atom feeds. No popularity signal upstream, so score is recency-only.

    Tolerates both ``<rss><channel><item>`` and ``<feed><entry>`` shapes.
    """
    try:
        body = _http_get(feed_url)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.warning("rss fetch failed (%s): %s", feed_url, e)
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        log.warning("rss parse failed (%s): %s", feed_url, e)
        return []

    items = _rss_items(root)
    out: list[Snippet] = []
    for entry in items[:limit]:
        title = (entry.get("title") or "").strip()
        link = entry.get("link") or ""
        if not title or not link:
            continue
        published_at = entry.get("published_at")
        out.append(
            Snippet(
                source="rss",
                url=link,
                title=title,
                snippet=(entry.get("summary") or None),
                author=entry.get("author"),
                published_at=published_at,
                # No popularity → score is purely recency, but capped at 0.7 so
                # an HN/Reddit hit can still outrank a fresh RSS item.
                score=round(_recency_factor(published_at) * 0.7, 4),
                query=feed_url,
                extra={"feed": feed_url},
            )
        )
    return out


# ---------------------------------------------------------------------------
# Orchestration — fetch many sources in parallel, sort, dedupe, return.
# ---------------------------------------------------------------------------


@dataclass
class ResearchRequest:
    queries: list[str] = field(default_factory=list)  # for hn, devto, reddit
    rss_feeds: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=lambda: ["hn", "devto", "reddit", "rss"])
    per_source_limit: int = PER_SOURCE_LIMIT


SOURCE_FETCHERS: dict[str, Callable[[str, int], list[Snippet]]] = {
    "hn": lambda q, n: fetch_hn(q, limit=n),
    "devto": lambda q, n: fetch_devto(q, limit=n),
    "reddit": lambda q, n: fetch_reddit(q, limit=n),
    "rss": lambda q, n: fetch_rss(q, limit=n),
}


def run_research(req: ResearchRequest) -> list[Snippet]:
    """Run every (source, query/feed) pair in parallel, dedupe by URL, sort by score.

    Concurrent fetch is the critical bit — Reddit alone can take 2–3s, and
    blocking the whole loop on it would push P50 latency above 10s. With the
    pool, total wall-time is ~max(per-source) + small overhead.
    """
    jobs: list[tuple[str, str]] = []
    for src in req.sources:
        if src == "rss":
            jobs.extend(("rss", feed) for feed in req.rss_feeds)
        elif src in SOURCE_FETCHERS:
            jobs.extend((src, q) for q in req.queries if q.strip())

    if not jobs:
        return []

    results: list[Snippet] = []
    # ``min(8, len(jobs))`` — one worker per job up to a small ceiling so we
    # don't spin up dozens of threads for a research request with many feeds.
    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
        futures = {
            pool.submit(SOURCE_FETCHERS[src], q, req.per_source_limit): (src, q)
            for src, q in jobs
        }
        for fut in as_completed(futures):
            src, q = futures[fut]
            try:
                results.extend(fut.result())
            except Exception as e:  # noqa: BLE001 — we never want one source to crash the run.
                log.warning("source %s/%s raised: %s", src, q, e)

    return _dedupe_by_url(sorted(results, key=lambda s: s.score, reverse=True))


def format_for_prompt(snippets: Iterable[Snippet], *, max_chars: int = 1800) -> str:
    """Render snippets as a compact markdown block to drop into an LLM prompt.

    Capped to ``max_chars`` so we don't blow the context window when the user
    has hundreds of snippets banked.
    """
    lines: list[str] = []
    for s in snippets:
        # Plenty of detail for the model, no formatting that confuses Llama.
        line = f"- [{s.source}] {s.title} ({s.url})"
        if s.snippet:
            tail = s.snippet.strip().replace("\n", " ")
            if len(tail) > 180:
                tail = tail[:177] + "..."
            line += f"\n    {tail}"
        lines.append(line)
        if sum(len(line_) + 1 for line_ in lines) > max_chars:
            break
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _dedupe_by_url(snippets: list[Snippet]) -> list[Snippet]:
    seen: set[str] = set()
    out: list[Snippet] = []
    for s in snippets:
        if s.url in seen:
            continue
        seen.add(s.url)
        out.append(s)
    return out


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    # HN/Dev.to use ``2026-04-26T12:00:00Z`` — Python's ``fromisoformat`` rejects
    # the trailing Z before 3.11. Replace it for compat.
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None


def _from_unix(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _rss_items(root: ET.Element) -> list[dict]:
    """Extract a normalised list of dicts from RSS or Atom XML.

    We don't validate the XML — feeds in the wild are messy. We probe for the
    fields we care about and fall back to ``None`` when something's missing.
    """
    items: list[dict] = []

    # RSS 2.0
    for item in root.iter("item"):
        items.append(
            {
                "title": _text(item.find("title")),
                "link": _text(item.find("link")),
                "summary": _text(item.find("description")),
                "author": _text(item.find("{http://purl.org/dc/elements/1.1/}creator"))
                or _text(item.find("author")),
                "published_at": _parse_iso(_text(item.find("pubDate"))),
            }
        )

    # Atom — namespaced. Match by local-name suffix to dodge xmlns mismatches.
    for entry in _iter_local(root, "entry"):
        link_el = _find_local(entry, "link")
        link = (link_el.get("href") if link_el is not None else None) or _text(link_el)
        items.append(
            {
                "title": _text(_find_local(entry, "title")),
                "link": link,
                "summary": _text(_find_local(entry, "summary"))
                or _text(_find_local(entry, "content")),
                "author": _text(_find_local(_find_local(entry, "author"), "name"))
                if _find_local(entry, "author") is not None
                else None,
                "published_at": _parse_iso(_text(_find_local(entry, "published")))
                or _parse_iso(_text(_find_local(entry, "updated"))),
            }
        )

    return items


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


def _iter_local(root: ET.Element, name: str) -> Iterable[ET.Element]:
    suffix = f"}}{name}"
    for el in root.iter():
        tag = el.tag
        if tag == name or tag.endswith(suffix):
            yield el


def _find_local(parent: ET.Element | None, name: str) -> ET.Element | None:
    if parent is None:
        return None
    suffix = f"}}{name}"
    for el in parent:
        if el.tag == name or el.tag.endswith(suffix):
            return el
    return None
