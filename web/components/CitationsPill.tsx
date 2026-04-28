"use client";

/**
 * Tiny pill that surfaces "this draft was grounded by N research signals."
 * Lazy-fetches the snippet titles on first open to avoid an N+1 stampede when
 * many cards mount at once — only drafts the user actually inspects pay the
 * round-trip.
 */

import { useState } from "react";
import { ExternalLink, Loader2, Newspaper } from "lucide-react";
import { api, ResearchSnippet } from "@/lib/api";

const SOURCE_LABEL: Record<string, string> = {
  hn: "HN",
  devto: "Dev.to",
  reddit: "Reddit",
  rss: "RSS",
};

export function CitationsPill({
  draftId,
  count,
}: {
  draftId: string;
  count: number;
}) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [snippets, setSnippets] = useState<ResearchSnippet[]>([]);
  const [error, setError] = useState<string | null>(null);

  if (count <= 0) return null;

  const toggle = async (e: React.MouseEvent) => {
    e.stopPropagation(); // don't trip the parent card's select-toggle
    const next = !open;
    setOpen(next);
    if (next && !loaded && !loading) {
      setLoading(true);
      setError(null);
      try {
        const out = await api.citations(draftId);
        setSnippets(out.snippets);
        setLoaded(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="relative inline-block" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={toggle}
        className="inline-flex items-center gap-1 rounded-full border border-violet-400/30 bg-violet-500/10 px-2 py-0.5 text-[10px] font-medium text-violet-200 hover:bg-violet-500/20 transition-colors"
        aria-expanded={open}
        aria-label={`${count} research signal${count === 1 ? "" : "s"} grounded this draft`}
      >
        <Newspaper size={10} />
        {count} signal{count === 1 ? "" : "s"}
      </button>

      {open && (
        <div
          className="absolute z-30 right-0 mt-1.5 w-72 rounded-xl border border-white/10 bg-black/95 p-3 shadow-2xl backdrop-blur-xl"
          // Stop click propagation on the popover itself so users can interact
          // with links / scrollbars without toggling the parent card.
          onClick={(e) => e.stopPropagation()}
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
            Grounded by
          </div>
          {loading ? (
            <div className="text-xs text-white/50 flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin" /> loading...
            </div>
          ) : error ? (
            <div className="text-xs text-rose-300">{error}</div>
          ) : snippets.length === 0 ? (
            // The snippet may have been deleted from the bank since the draft
            // was generated. Don't show a misleading "0" — explain what's up.
            <div className="text-xs text-white/50">
              Citations no longer in your bank.
            </div>
          ) : (
            <ul className="space-y-1.5">
              {snippets.map((s) => (
                <li key={s.id} className="text-xs">
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-start gap-1.5 text-white/85 hover:text-violet-200 leading-tight"
                  >
                    <span className="text-[9px] font-mono uppercase text-white/40 mt-0.5 shrink-0">
                      {SOURCE_LABEL[s.source] ?? s.source}
                    </span>
                    <span className="line-clamp-2 flex-1">{s.title}</span>
                    <ExternalLink size={9} className="opacity-50 mt-0.5 shrink-0" />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
