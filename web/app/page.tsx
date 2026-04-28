"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, Draft, Platform, Status } from "@/lib/api";
import {
  PLATFORMS,
  PLATFORM_BY_ID,
  PLATFORM_GROUPS,
  capabilityBadge,
} from "@/lib/platforms";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Clock,
  ExternalLink,
  Loader2,
  Newspaper,
  Send,
  Sparkles,
  Wand2,
  Zap,
} from "lucide-react";
import Rotator from "@/components/Rotator";
import Marquee from "@/components/Marquee";
import Spotlight from "@/components/Spotlight";
import AnimatedNumber from "@/components/AnimatedNumber";
import Typewriter from "@/components/Typewriter";

export default function Home() {
  const [product, setProduct] = useState("");
  const [platform, setPlatform] = useState<Platform>("linkedin");
  const [loading, setLoading] = useState(false);
  const [variations, setVariations] = useState<Draft[]>([]);
  const [variationsKey, setVariationsKey] = useState(0); // bumps to retrigger typewriter
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<Draft[]>([]);
  const [useResearch, setUseResearch] = useState(false);
  // Number of *unused* research snippets the agent could fold into the next
  // run. Refreshed alongside `recent` so the indicator stays live.
  const [researchCount, setResearchCount] = useState<number | null>(null);

  const meta = PLATFORM_BY_ID[platform];

  async function refreshRecent() {
    try {
      const all = await api.list();
      setRecent(all.filter((d) => d.status !== "pending").slice(0, 8));
    } catch {}
  }

  async function refreshResearchCount() {
    try {
      const list = await api.research.list({ only_unused: true, limit: 100 });
      setResearchCount(list.length);
    } catch {
      // Silently ignore — older backends without /research endpoints just
      // leave the indicator hidden.
      setResearchCount(null);
    }
  }

  useEffect(() => {
    refreshRecent();
    refreshResearchCount();
    const t = setInterval(refreshRecent, 5000);
    return () => clearInterval(t);
  }, []);

  async function generate() {
    setError(null);
    setLoading(true);
    setVariations([]);
    setSelected(new Set());
    try {
      const out = await api.variations(product, platform, 5, { useResearch });
      setVariations(out.drafts);
      setVariationsKey((k) => k + 1); // re-trigger typewriter
      // After a research-grounded run the unused count drops — refresh.
      if (useResearch) void refreshResearchCount();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function postSelected() {
    if (selected.size === 0) return;
    setPosting(true);
    try {
      await api.queueBulk([...selected]);
      const queuedIds = new Set(selected);
      setVariations((prev) => prev.filter((d) => !queuedIds.has(d.id)));
      setSelected(new Set());
      await refreshRecent();
    } catch (e) {
      setError(String(e));
    } finally {
      setPosting(false);
    }
  }

  async function editVariation(id: string, content: string) {
    await api.edit(id, content);
    setVariations((prev) => prev.map((d) => (d.id === id ? { ...d, content } : d)));
  }

  function statusStyle(status: Status) {
    const map: Record<Status, string> = {
      pending: "bg-white/5 text-white/50 ring-1 ring-white/10",
      queued: "bg-blue-500/15 text-blue-300 ring-1 ring-blue-400/20",
      scheduled: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-400/20",
      posting: "bg-violet-500/15 text-violet-300 ring-1 ring-violet-400/20 animate-pulse",
      posted: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/20",
      failed: "bg-rose-500/15 text-rose-300 ring-1 ring-rose-400/20",
    };
    return map[status];
  }

  const groups = useMemo(
    () =>
      PLATFORM_GROUPS.map((g) => ({
        ...g,
        items: PLATFORMS.filter((p) => p.group === g.id),
      })),
    []
  );

  const wordCount = product.trim().split(/\s+/).filter(Boolean).length;
  const ready = product.length >= 10;

  const verb =
    meta.capability === "auto"
      ? "Post"
      : meta.capability === "mailto"
      ? "Open"
      : meta.capability === "assist"
      ? "Send"
      : "Copy & open";

  // Words for the rotator — quick brand names from PLATFORMS
  const rotatorWords = useMemo(() => PLATFORMS.map((p) => p.label), []);

  return (
    <main className="min-h-screen pb-32">
      <div className="mx-auto max-w-6xl px-6 py-14 space-y-20">
        {/* HERO */}
        <header className="space-y-7 text-center pt-8">
          <a
            href="#composer"
            className="group inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-xs text-white/70 hover:bg-white/[0.07] transition-colors"
          >
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-60" />
              <span className="relative h-1.5 w-1.5 rounded-full bg-emerald-400" />
            </span>
            <span>15 channels live</span>
            <span className="text-white/30">·</span>
            <span>powered by free models</span>
            <ArrowRight size={11} className="ml-0.5 transition-transform group-hover:translate-x-0.5" />
          </a>

          <h1 className="text-5xl sm:text-7xl font-bold tracking-[-0.04em] gradient-text leading-[1.05]">
            Ship to{" "}
            <Rotator
              words={rotatorWords}
              className="text-white"
            />
            <br />
            without every account.
          </h1>

          <p className="text-lg text-white/55 max-w-2xl mx-auto leading-relaxed">
            One prompt. Five distinct drafts. Posted from your own browser session — no API
            keys, no spam fingerprint, no monthly seat fees.
          </p>

          {/* Stats strip with count-up */}
          <div className="flex flex-wrap items-center justify-center gap-8 pt-4 text-sm text-white/55">
            <Stat icon={<Zap size={14} />}>
              ~<AnimatedNumber value={10} className="font-semibold text-white" />s to 5 drafts
            </Stat>
            <span className="text-white/10">·</span>
            <Stat icon={<Sparkles size={14} />}>
              <AnimatedNumber value={15} className="font-semibold text-white" /> channels
            </Stat>
            <span className="text-white/10">·</span>
            <Stat icon={<CheckCircle2 size={14} />}>
              <AnimatedNumber value={0} className="font-semibold text-white" /> API keys needed
            </Stat>
          </div>

          {/* Marquee logo cloud */}
          <div className="pt-4">
            <Marquee speedSeconds={32}>
              {PLATFORMS.map(({ id, label, Icon }) => (
                <div
                  key={id}
                  className="flex items-center gap-2 text-white/35 hover:text-white/85 transition-colors cursor-default"
                  title={label}
                >
                  <Icon size={20} />
                  <span className="text-sm font-medium">{label}</span>
                </div>
              ))}
            </Marquee>
          </div>
        </header>

        {/* COMPOSER */}
        <section
          id="composer"
          className="fanout-conic glass rounded-3xl p-8 sm:p-10 space-y-10"
        >
          {/* Product */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2.5 text-sm font-medium text-white/85">
                <span className="step-num">1</span>
                What are you launching?
              </label>
              <span className="text-xs text-white/35 tabular-nums">{wordCount} words</span>
            </div>
            <textarea
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              rows={5}
              placeholder="Fanout — an agentic content studio that drafts platform-tailored posts and ships them through your own browser session. No third-party API keys, no spam-detection fingerprint."
              className="input resize-none text-[15px] leading-relaxed"
            />
          </div>

          {/* Platform */}
          <div className="space-y-5">
            <label className="flex items-center gap-2.5 text-sm font-medium text-white/85">
              <span className="step-num">2</span>
              Where does it go?
            </label>

            {groups.map((g) => (
              <div key={g.id} className="space-y-2.5">
                <div className="flex items-center gap-3">
                  <span className="text-[10px] uppercase tracking-[0.2em] text-white/35 font-semibold">
                    {g.label}
                  </span>
                  <div className="h-px flex-1 bg-gradient-to-r from-white/8 to-transparent" />
                  <span className="text-[10px] text-white/30">{g.hint}</span>
                </div>
                <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2.5">
                  {g.items.map((p) => {
                    const active = platform === p.id;
                    const cap = capabilityBadge(p.capability);
                    const Icon = p.Icon;
                    return (
                      <Spotlight key={p.id} color={`${p.accent}33`} className="rounded-xl">
                        <button
                          type="button"
                          onClick={() => setPlatform(p.id)}
                          className={`group relative w-full overflow-hidden rounded-xl border p-3 text-left transition-all duration-200
                            ${active
                              ? "border-white/30 bg-white/[0.07] shadow-[0_8px_24px_-12px_rgba(255,255,255,0.15)]"
                              : "border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]"
                            }`}
                          title={`${p.label} · ${cap.label}`}
                        >
                          {active && (
                            <>
                              <div
                                className="absolute -top-px -left-px -right-px h-px"
                                style={{ background: `linear-gradient(90deg, transparent, ${p.accent}, transparent)` }}
                              />
                              <div
                                className="absolute -inset-1 -z-10 opacity-30 blur-2xl"
                                style={{ background: p.accent }}
                              />
                            </>
                          )}
                          <div
                            className={`mb-2 transition-colors ${active ? "" : "text-white/60 group-hover:text-white/85"}`}
                            style={active ? { color: p.accent } : undefined}
                          >
                            <Icon size={20} />
                          </div>
                          <div className={`text-[12px] font-medium ${active ? "text-white" : "text-white/70"}`}>
                            {p.label}
                          </div>
                          <div className={`mt-1 text-[9px] uppercase tracking-wider ${cap.tone} inline-flex items-center px-1.5 py-0.5 rounded`}>
                            {cap.label}
                          </div>
                        </button>
                      </Spotlight>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* Research toggle — only surfaces if the backend has snippets banked */}
          {researchCount !== null && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/[0.08] bg-white/[0.02] px-4 py-3">
              <label className="flex items-center gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={useResearch}
                  onChange={(e) => setUseResearch(e.target.checked)}
                  disabled={researchCount === 0}
                  className="h-4 w-4 accent-violet-400 disabled:opacity-40"
                />
                <span className="text-sm flex items-center gap-2">
                  <Newspaper size={14} className="text-violet-300" />
                  Use live research
                  <span className="text-xs text-white/50">
                    {researchCount === 0
                      ? "no banked snippets — fetch some first"
                      : `${researchCount} unused snippet${researchCount === 1 ? "" : "s"} ready`}
                  </span>
                </span>
              </label>
              <Link
                href="/research"
                className="text-xs text-violet-300 hover:text-violet-200 inline-flex items-center gap-1"
              >
                Open research workbench
                <ArrowRight size={11} />
              </Link>
            </div>
          )}

          {/* CTA */}
          <div className="flex flex-wrap items-center justify-between gap-4 pt-2">
            <div className="flex items-center gap-2.5 text-xs text-white/40">
              <span className="step-num">3</span>
              5 distinct angles · ~10 seconds
            </div>
            <button onClick={generate} disabled={loading || !ready} className="btn-primary">
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Crafting drafts…
                </>
              ) : (
                <>
                  <Wand2 size={16} />
                  Generate 5 drafts
                  <ArrowRight size={14} />
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {error}
            </div>
          )}
        </section>

        {/* SKELETONS */}
        {loading && (
          <section className="space-y-4">
            {[0, 1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="glass rounded-2xl p-6 space-y-3 fade-up"
                style={{ animationDelay: `${i * 80}ms` }}
              >
                <div className="h-4 w-32 rounded shimmer" />
                <div className="h-3 w-full rounded shimmer" />
                <div className="h-3 w-5/6 rounded shimmer" />
                <div className="h-3 w-2/3 rounded shimmer" />
              </div>
            ))}
          </section>
        )}

        {/* VARIATIONS */}
        {variations.length > 0 && (
          <section className="space-y-6" key={variationsKey}>
            <div className="flex items-end justify-between flex-wrap gap-3">
              <div>
                <div className="text-xs uppercase tracking-[0.2em] text-white/40 mb-1.5">
                  Step 4
                </div>
                <h2 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
                  Pick your favorites
                  <span className="inline-flex items-center gap-1.5 text-base text-white/60 font-normal">
                    for <meta.Icon size={18} style={{ color: meta.accent }} /> {meta.label}
                  </span>
                </h2>
                <p className="text-sm text-white/45 mt-1.5">
                  Click cards to select. {selected.size} of {variations.length} chosen.
                </p>
              </div>
            </div>

            <div className="space-y-4">
              {variations.map((d, i) => {
                const isSelected = selected.has(d.id);
                return (
                  <Spotlight key={d.id} className="rounded-2xl">
                    <article
                      onClick={() => toggle(d.id)}
                      className={`group fade-up rounded-2xl p-6 cursor-pointer transition-all duration-200
                        ${isSelected
                          ? "border border-violet-500/50 bg-gradient-to-br from-violet-500/10 to-fuchsia-500/[0.04] shadow-[0_0_0_1px_rgba(139,92,246,0.3),0_24px_60px_-12px_rgba(139,92,246,0.3)]"
                          : "border border-white/10 bg-white/[0.025] hover:bg-white/[0.045] hover:border-white/20"
                        }`}
                      style={{ animationDelay: `${i * 60}ms` }}
                    >
                      <header className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div
                            className={`flex h-7 w-7 items-center justify-center rounded-lg text-xs font-mono transition-all
                              ${isSelected
                                ? "bg-violet-500 text-white shadow-lg"
                                : "bg-white/10 text-white/60 group-hover:bg-white/15"
                              }`}
                          >
                            {isSelected ? <Check size={14} /> : i + 1}
                          </div>
                          {d.feedback && (
                            <span className="badge bg-white/5 text-white/60 ring-1 ring-white/10">
                              {d.feedback}
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] tabular-nums text-white/40">
                          {d.content.length} chars
                        </span>
                      </header>
                      {/* Typewriter overlay; clicking it edits via the textarea below */}
                      <div className="relative">
                        <pre
                          aria-hidden="true"
                          className="absolute inset-0 m-0 whitespace-pre-wrap break-words text-sm font-mono text-white/90 leading-relaxed pointer-events-none"
                        >
                          <Typewriter text={d.content} />
                        </pre>
                        <textarea
                          defaultValue={d.content}
                          onClick={(e) => e.stopPropagation()}
                          onBlur={(e) => {
                            if (e.target.value !== d.content) editVariation(d.id, e.target.value);
                          }}
                          rows={Math.min(14, Math.ceil(d.content.length / 80) + 2)}
                          className="w-full bg-transparent text-sm font-mono text-transparent caret-violet-400 leading-relaxed
                                     resize-none focus:outline-none placeholder:text-white/30 selection:bg-violet-500/30"
                          style={{ caretColor: "#a78bfa" }}
                        />
                      </div>
                    </article>
                  </Spotlight>
                );
              })}
            </div>
          </section>
        )}

        {/* RECENT */}
        {recent.length > 0 && (
          <section className="space-y-4">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold tracking-tight">Activity</h2>
              <div className="h-px flex-1 bg-white/[0.06]" />
              <span className="text-xs text-white/40">last {recent.length}</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {recent.map((d) => {
                const m = PLATFORM_BY_ID[d.platform];
                const Icon = m?.Icon;
                return (
                  <Spotlight key={d.id} className="rounded-xl">
                    <article className="glass rounded-xl p-4 space-y-2.5 glass-hover">
                      <header className="flex items-center justify-between">
                        <span className="text-[11px] font-medium flex items-center gap-2 text-white/70">
                          {Icon && <Icon size={13} style={{ color: m.accent }} />}
                          <span className="uppercase tracking-widest text-white/55">
                            {m?.label ?? d.platform}
                          </span>
                        </span>
                        <span className={`badge ${statusStyle(d.status)}`}>{d.status}</span>
                      </header>
                      <p className="text-sm text-white/70 line-clamp-3 whitespace-pre-wrap">
                        {d.content}
                      </p>
                      <div className="flex items-center justify-between pt-1">
                        <span className="text-[10px] text-white/30 inline-flex items-center gap-1">
                          <Clock size={10} />
                          {new Date(d.created_at).toLocaleString(undefined, {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                        {d.post_url && (
                          <a
                            href={d.post_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-[11px] text-violet-300 hover:text-violet-200 inline-flex items-center gap-1"
                          >
                            View <ExternalLink size={10} />
                          </a>
                        )}
                      </div>
                      {d.error && <p className="text-[11px] text-rose-300/80">{d.error}</p>}
                    </article>
                  </Spotlight>
                );
              })}
            </div>
          </section>
        )}
      </div>

      {/* STICKY ACTION BAR */}
      {selected.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 fade-up">
          <div className="glass rounded-2xl px-4 py-3 flex items-center gap-4 shadow-2xl">
            <div className="flex items-center gap-2 pl-1">
              <span className="flex h-7 min-w-[1.75rem] items-center justify-center rounded-full bg-violet-500/20 text-xs font-semibold text-violet-200 px-2">
                {selected.size}
              </span>
              <span className="text-sm text-white/70 inline-flex items-center gap-1.5">
                for
                <meta.Icon size={14} style={{ color: meta.accent }} />
                <span className="text-white/90 font-medium">{meta.label}</span>
              </span>
            </div>
            <div className="h-6 w-px bg-white/10" />
            <button
              onClick={() => setSelected(new Set())}
              className="text-sm text-white/50 hover:text-white/80 transition-colors"
            >
              Clear
            </button>
            <button onClick={postSelected} disabled={posting} className="btn-success">
              {posting ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Sending…
                </>
              ) : (
                <>
                  <Send size={14} />
                  {verb} {selected.size}
                  <ArrowRight size={12} />
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

function Stat({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-violet-300">{icon}</span>
      <span className="text-white/85">{children}</span>
    </div>
  );
}
