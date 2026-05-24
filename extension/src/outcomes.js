// Engagement-metric extractor — injected into the open post page via
// chrome.scripting.executeScript. Runs in the page's isolated world and
// returns a plain object the background worker turns into outcome rows.
//
// Strategy: prefer aria-label patterns first (X / Bluesky / Threads use
// data-testid + aria-label idioms that are stable across redesigns), then
// fall back to scanning visible text for `<NUMBER> <metric-word>` pairs.
// Text-scanning is platform-agnostic so it works for Mastodon, LinkedIn,
// and any platform we add later without selector maintenance.
//
// Returns: { metrics: { likes, comments, reposts, views, ... }, source }
// where each metric is an integer (already normalized from "1.2K" / "1,234")
// and ``source`` is a short string explaining which extractor matched.

(function () {
  const METRIC_WORDS = {
    likes: ["like", "likes", "favorite", "favorites", "favourite", "favourites"],
    comments: ["comment", "comments", "reply", "replies"],
    reposts: ["repost", "reposts", "retweet", "retweets", "boost", "boosts", "reblog", "reblogs", "share", "shares"],
    views: ["view", "views", "impression", "impressions"],
    clicks: ["click", "clicks", "tap", "taps"],
    saves: ["save", "saves", "bookmark", "bookmarks"],
  };

  function parseCount(raw) {
    if (raw == null) return null;
    const s = String(raw).trim().replace(/,/g, "");
    const m = s.match(/^(\d+(?:\.\d+)?)([KkMmBb])?$/);
    if (!m) return null;
    const n = parseFloat(m[1]);
    const mul = ({ K: 1e3, M: 1e6, B: 1e9 })[(m[2] || "").toUpperCase()] || 1;
    return Math.round(n * mul);
  }

  // Walk every aria-label on the page; if it looks like "<number> <metric>"
  // record the max value per kind. Max is the safest reducer when the same
  // page may show the metric in multiple places (button + tooltip).
  function fromAriaLabels() {
    const out = {};
    const nodes = document.querySelectorAll("[aria-label]");
    for (const node of nodes) {
      const label = node.getAttribute("aria-label") || "";
      // Match "1,234 likes" / "1.2K views" / "12 replies" anywhere in the label.
      const matches = label.match(/(\d+(?:[,.]\d+)*[KkMmBb]?)\s+([a-zA-Z]+)/g) || [];
      for (const m of matches) {
        const parts = m.match(/(\d+(?:[,.]\d+)*[KkMmBb]?)\s+([a-zA-Z]+)/);
        if (!parts) continue;
        const value = parseCount(parts[1]);
        if (value == null) continue;
        const word = parts[2].toLowerCase();
        for (const [kind, words] of Object.entries(METRIC_WORDS)) {
          if (words.includes(word) && (out[kind] == null || value > out[kind])) {
            out[kind] = value;
          }
        }
      }
    }
    return out;
  }

  // Text fallback — scan innerText for "<NUMBER> <metric-word>" pairs.
  function fromVisibleText() {
    const out = {};
    const text = (document.body && document.body.innerText) || "";
    // Limit scan: a busy feed page can have thousands of these; we only
    // want the ones near the post we're inspecting. URL-based filtering
    // happens at the background-worker level (we open the post's own URL),
    // so the first dozen matches on the page are usually the right ones.
    const re = /(\d+(?:[,.]\d+)*[KkMmBb]?)\s+([a-zA-Z]+)/g;
    let m;
    let scanned = 0;
    while ((m = re.exec(text)) !== null && scanned < 200) {
      scanned++;
      const value = parseCount(m[1]);
      if (value == null) continue;
      const word = m[2].toLowerCase();
      for (const [kind, words] of Object.entries(METRIC_WORDS)) {
        if (words.includes(word) && (out[kind] == null || value > out[kind])) {
          out[kind] = value;
        }
      }
    }
    return out;
  }

  function merge(primary, secondary) {
    const out = { ...secondary, ...primary };
    // Prefer the larger value when both extractors found the kind: the page
    // typically renders the more accurate count in the aria-label and a
    // shorter "12K" rounded form in visible text. Take max to avoid losing
    // precision.
    for (const k of Object.keys(out)) {
      const a = primary[k];
      const b = secondary[k];
      if (a != null && b != null) out[k] = Math.max(a, b);
    }
    return out;
  }

  function extract() {
    const aria = fromAriaLabels();
    const text = fromVisibleText();
    const metrics = merge(aria, text);
    let source = "none";
    if (Object.keys(aria).length > 0 && Object.keys(text).length > 0) source = "aria+text";
    else if (Object.keys(aria).length > 0) source = "aria";
    else if (Object.keys(text).length > 0) source = "text";
    return { metrics, source };
  }

  // Expose for both direct injection via `func:` and content_scripts loading.
  // chrome.scripting.executeScript with `files:` runs this module top-level;
  // background.js then calls window.__fanoutExtractMetrics().
  window.__fanoutExtractMetrics = extract;
})();
