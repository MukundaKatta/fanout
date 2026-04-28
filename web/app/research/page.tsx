"use client";

/**
 * Research workbench — bank live signals so the agent can ground future drafts.
 *
 * The page is intentionally simple: type queries (HN/Dev.to/Reddit) and/or RSS
 * feed URLs, fire `/research`, see the resulting snippets sorted by score.
 * Snippets the agent has already consumed are dimmed but still listed so the
 * user can audit what fed into a draft.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ExternalLink,
  Loader2,
  Newspaper,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { api, ResearchSnippet, ResearchSource } from "@/lib/api";

const ALL_SOURCES: ResearchSource[] = ["hn", "devto", "reddit", "rss"];

const SOURCE_META: Record<ResearchSource, { label: string; tone: string }> = {
  hn: { label: "Hacker News", tone: "from-orange-500/20 to-orange-500/5 border-orange-400/30" },
  devto: { label: "Dev.to", tone: "from-cyan-500/20 to-cyan-500/5 border-cyan-400/30" },
  reddit: { label: "Reddit", tone: "from-rose-500/20 to-rose-500/5 border-rose-400/30" },
  rss: { label: "RSS", tone: "from-violet-500/20 to-violet-500/5 border-violet-400/30" },
};

export default function ResearchPage() {
  const [queries, setQueries] = useState<string[]>([""]);
  const [feeds, setFeeds] = useState<string[]>([]);
  const [feedDraft, setFeedDraft] = useState("");
  const [running, setRunning] = useState(false);
  const [filter, setFilter] = useState<"all" | "unused">("unused");
  const [snippets, setSnippets] = useState<ResearchSnippet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<number | null>(null);

  // "Suggest from product" — the model converts a product blurb into
  // 5 short search queries. Cuts the cold-start friction for first-time
  // users who don't know what to type.
  const [suggestProduct, setSuggestProduct] = useState("");
  const [suggesting, setSuggesting] = useState(false);
  const [suggestionsApplied, setSuggestionsApplied] = useState(false);

  const suggestQueries = async () => {
    if (suggestProduct.trim().length < 10) {
      setError("Add a product description (10+ chars) to get suggestions.");
      return;
    }
    setSuggesting(true);
    setError(null);
    try {
      const out = await api.research.suggest(suggestProduct.trim(), 5);
      if (out.queries.length === 0) {
        setError("No suggestions returned — try a more descriptive product blurb.");
        return;
      }
      // Replace empty inputs first, then append the rest. This way an
      // existing partial draft isn't trampled but we still surface the
      // full suggestion set.
      setQueries((prev) => {
        const filled = [...prev];
        let cursor = 0;
        for (const q of out.queries) {
          while (cursor < filled.length && filled[cursor].trim()) cursor++;
          if (cursor < filled.length) {
            filled[cursor] = q;
            cursor++;
          } else {
            filled.push(q);
          }
        }
        return filled;
      });
      setSuggestionsApplied(true);
      // Brief flash — clear the "applied" indicator so the user can re-run.
      setTimeout(() => setSuggestionsApplied(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSuggesting(false);
    }
  };

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.research.list({
        only_unused: filter === "unused",
        limit: 100,
      });
      setSnippets(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const runResearch = async () => {
    const cleanQueries = queries.map((q) => q.trim()).filter(Boolean);
    const cleanFeeds = feeds.map((f) => f.trim()).filter(Boolean);
    if (cleanQueries.length === 0 && cleanFeeds.length === 0) {
      setError("Add at least one query or RSS feed.");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const result = await api.research.run({
        queries: cleanQueries,
        rss_feeds: cleanFeeds,
        sources: ALL_SOURCES,
      });
      setLastFetched(result.fetched);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const counts = useMemo(() => {
    const byUnused = snippets.filter((s) => !s.used_in_draft_id).length;
    return { total: snippets.length, unused: byUnused, used: snippets.length - byUnused };
  }, [snippets]);

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="flex items-center justify-between mb-8">
        <Link
          href="/"
          className="text-xs text-white/50 hover:text-white inline-flex items-center gap-1.5 transition-colors"
        >
          <ArrowLeft size={14} />
          Back to composer
        </Link>
        <span className="text-[11px] font-mono text-white/40 uppercase tracking-wider">
          Research workbench
        </span>
      </header>

      <h1 className="text-3xl font-semibold tracking-tight mb-2">
        Ground drafts in <span className="text-violet-300">live conversation</span>
      </h1>
      <p className="text-white/60 max-w-2xl mb-8">
        Pull current signals from Hacker News, Dev.to, Reddit, and any RSS feed. The next
        time you generate with <em>use research</em> on, the agent gets the top unused
        snippets folded into its planning prompt.
      </p>

      {/* Suggest queries from product blurb — kills cold-start friction */}
      <section className="rounded-xl border border-violet-400/20 bg-violet-500/[0.04] p-5 mb-4">
        <div className="flex items-center justify-between gap-2 mb-3">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Wand2 size={14} className="text-violet-300" />
            Don&apos;t know what to track? Suggest from your product
          </h2>
          {suggestionsApplied && (
            <span className="text-xs text-emerald-300">Added 5 queries below</span>
          )}
        </div>
        <div className="flex gap-2 items-stretch">
          <textarea
            value={suggestProduct}
            onChange={(e) => setSuggestProduct(e.target.value)}
            placeholder="Paste your product description — same text you'd put in the composer..."
            rows={2}
            className="flex-1 rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm focus:outline-none focus:border-violet-400/50 resize-none"
          />
          <button
            onClick={suggestQueries}
            disabled={suggesting || suggestProduct.trim().length < 10}
            className="rounded-lg border border-violet-400/30 bg-violet-500/15 px-3 text-xs font-medium hover:bg-violet-500/25 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1.5 whitespace-nowrap"
          >
            {suggesting ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Sparkles size={12} />
            )}
            {suggesting ? "Thinking..." : "Suggest 5"}
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-white/10 bg-white/[0.03] p-5 mb-8">
        <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
          <Search size={14} className="text-violet-300" />
          Run research
        </h2>

        <div className="space-y-3 mb-4">
          <label className="text-[11px] font-mono text-white/40 uppercase tracking-wider">
            Queries (HN · Dev.to · Reddit)
          </label>
          {queries.map((q, i) => (
            <div key={i} className="flex gap-2">
              <input
                value={q}
                onChange={(e) =>
                  setQueries((prev) => prev.map((p, idx) => (idx === i ? e.target.value : p)))
                }
                placeholder="e.g. ai agents, content automation, indie hackers"
                className="flex-1 rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm focus:outline-none focus:border-violet-400/50"
              />
              {queries.length > 1 && (
                <button
                  onClick={() =>
                    setQueries((prev) => prev.filter((_, idx) => idx !== i))
                  }
                  className="px-2 text-white/40 hover:text-white transition-colors"
                  aria-label="Remove query"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          ))}
          <button
            onClick={() => setQueries((prev) => [...prev, ""])}
            disabled={queries.length >= 10}
            className="text-xs text-violet-300 hover:text-violet-200 inline-flex items-center gap-1 disabled:opacity-30"
          >
            <Plus size={12} /> add query
          </button>
        </div>

        <div className="space-y-3 mb-4">
          <label className="text-[11px] font-mono text-white/40 uppercase tracking-wider">
            RSS / Atom feeds
          </label>
          {feeds.length === 0 && (
            <p className="text-xs text-white/40">
              Optional — paste any feed URL to track a blog or community.
            </p>
          )}
          {feeds.map((f, i) => (
            <div key={i} className="flex gap-2 items-center">
              <span className="text-xs text-white/50 truncate flex-1 font-mono">{f}</span>
              <button
                onClick={() => setFeeds((prev) => prev.filter((_, idx) => idx !== i))}
                className="px-2 text-white/40 hover:text-white"
                aria-label="Remove feed"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          <div className="flex gap-2">
            <input
              value={feedDraft}
              onChange={(e) => setFeedDraft(e.target.value)}
              placeholder="https://example.com/feed.xml"
              className="flex-1 rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm focus:outline-none focus:border-violet-400/50"
            />
            <button
              onClick={() => {
                const v = feedDraft.trim();
                if (!v) return;
                setFeeds((prev) => [...prev, v]);
                setFeedDraft("");
              }}
              disabled={!feedDraft.trim() || feeds.length >= 10}
              className="px-3 rounded-lg border border-white/10 text-xs text-white/70 hover:bg-white/5 disabled:opacity-30"
            >
              Add
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={runResearch}
            disabled={running}
            className="rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 px-4 py-2 text-sm font-medium hover:brightness-110 disabled:opacity-50 inline-flex items-center gap-2"
          >
            {running ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {running ? "Fetching..." : "Run research"}
          </button>
          {lastFetched != null && !running && (
            <span className="text-xs text-white/50">
              Last run: {lastFetched} snippets fetched
            </span>
          )}
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Newspaper size={14} className="text-white/40" />
            <h2 className="text-sm font-semibold">Banked snippets</h2>
            <span className="text-xs text-white/50">
              {counts.unused} unused · {counts.used} used
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="rounded-full border border-white/10 p-0.5 text-[11px] flex">
              <button
                onClick={() => setFilter("unused")}
                className={`px-2.5 py-1 rounded-full transition-colors ${
                  filter === "unused" ? "bg-white/10 text-white" : "text-white/50"
                }`}
              >
                Unused
              </button>
              <button
                onClick={() => setFilter("all")}
                className={`px-2.5 py-1 rounded-full transition-colors ${
                  filter === "all" ? "bg-white/10 text-white" : "text-white/50"
                }`}
              >
                All
              </button>
            </div>
            <button
              onClick={() => void refresh()}
              className="text-xs text-white/50 hover:text-white inline-flex items-center gap-1"
            >
              <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
            {error}
          </div>
        )}

        {loading && snippets.length === 0 ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-10 text-center text-white/40">
            <Loader2 size={18} className="animate-spin mx-auto mb-2" />
            Loading snippets...
          </div>
        ) : snippets.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center text-white/50">
            No snippets yet. Run a research pass above to bank some.
          </div>
        ) : (
          <ul className="space-y-2">
            {snippets.map((s) => (
              <SnippetRow key={s.id} snippet={s} />
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function SnippetRow({ snippet }: { snippet: ResearchSnippet }) {
  const meta = SOURCE_META[snippet.source];
  const used = snippet.used_in_draft_id != null;
  return (
    <li
      className={`rounded-xl border bg-gradient-to-br p-4 transition-opacity ${meta.tone} ${
        used ? "opacity-50" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3 mb-1">
        <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider">
          <span className="text-white/70">{meta.label}</span>
          {snippet.query && <span className="text-white/40">· “{snippet.query}”</span>}
          {used && <span className="text-white/40">· used</span>}
        </div>
        <span className="text-[10px] font-mono text-white/40">
          score {snippet.score.toFixed(2)}
        </span>
      </div>
      <a
        href={snippet.url}
        target="_blank"
        rel="noreferrer"
        className="text-sm font-medium hover:text-violet-200 inline-flex items-center gap-1.5"
      >
        {snippet.title}
        <ExternalLink size={11} className="opacity-60" />
      </a>
      {snippet.snippet && (
        <p className="text-xs text-white/60 mt-1 line-clamp-2">{snippet.snippet}</p>
      )}
    </li>
  );
}
