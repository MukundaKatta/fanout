"use client";

/**
 * Engagement analytics — what the extension's outcome puller has brought back.
 *
 * Reads /analytics/engagement, which folds the append-only draft_outcomes
 * timeline into per-channel totals and a bucketed time series. Values are
 * *gains* (cumulative snapshots converted to increments), so the bars sum to
 * the headline tiles, which match the per-channel table.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, BarChart3, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { api, AnalyticsBucket, EngagementAnalytics, Platform } from "@/lib/api";
import { PLATFORM_BY_ID } from "@/lib/platforms";

const RANGES = [
  { days: 7, label: "7 days", bucket: "day" as AnalyticsBucket },
  { days: 30, label: "30 days", bucket: "day" as AnalyticsBucket },
  { days: 90, label: "90 days", bucket: "week" as AnalyticsBucket },
  { days: 365, label: "1 year", bucket: "week" as AnalyticsBucket },
];

// Canonical order for tiles + table columns; unknown kinds append alphabetically.
const KIND_ORDER = ["likes", "comments", "replies", "reposts", "shares", "saves", "clicks", "views"];

const fmt = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 1 });

export default function AnalyticsPage() {
  const [data, setData] = useState<EngagementAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rangeIdx, setRangeIdx] = useState(1);
  const [platform, setPlatform] = useState<Platform | "">("");
  const [metric, setMetric] = useState<string>("likes");

  const range = RANGES[rangeIdx];

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await api.analytics.engagement({
          days: range.days,
          bucket: range.bucket,
          platform: platform || undefined,
        })
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rangeIdx, platform]);

  const kinds = useMemo(() => {
    const seen = data?.metric_kinds ?? [];
    const known = KIND_ORDER.filter((k) => seen.includes(k));
    return [...known, ...seen.filter((k) => !KIND_ORDER.includes(k)).sort()];
  }, [data]);

  // Keep the chart metric valid when the data changes under it.
  useEffect(() => {
    if (kinds.length && !kinds.includes(metric)) setMetric(kinds[0]);
  }, [kinds, metric]);

  // Platform options come from an unfiltered view so the dropdown doesn't
  // shrink to one entry after filtering.
  const [knownPlatforms, setKnownPlatforms] = useState<Platform[]>([]);
  useEffect(() => {
    if (data && !platform) setKnownPlatforms(data.channels.map((c) => c.platform));
  }, [data, platform]);

  const empty = !!data && data.draft_count === 0;

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="flex items-center justify-between mb-8">
        <Link
          href="/research"
          className="text-xs text-white/50 hover:text-white inline-flex items-center gap-1.5 transition-colors"
        >
          <ArrowLeft size={12} />
          Back to research workbench
        </Link>
      </header>

      <div className="mb-6">
        <p className="text-[11px] uppercase tracking-wider text-violet-300/80 font-mono mb-1">
          ENGAGEMENT ANALYTICS
        </p>
        <h1 className="text-3xl font-bold tracking-tight mb-2">Which channels are earning attention</h1>
        <p className="text-sm text-white/60 max-w-3xl">
          Every metric the extension's outcome puller posts back to{" "}
          <code className="text-white/70 font-mono">/drafts/&#123;id&#125;/outcomes</code>, rolled up per
          channel and over time. Repeated pulls only count what they <em>added</em>, so 10 → 25 → 40
          likes is 40 likes, not 75. Views are shown but left out of the channel ranking.
        </p>
      </div>

      <section className="rounded-xl border border-white/10 bg-white/[0.03] p-5 mb-6">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-1 text-xs font-mono" role="group" aria-label="Time range">
            {RANGES.map((r, i) => (
              <button
                key={r.days}
                onClick={() => setRangeIdx(i)}
                aria-pressed={i === rangeIdx}
                className={`rounded-md border px-2.5 py-1 transition-colors ${
                  i === rangeIdx
                    ? "bg-white/10 border-white/30 text-white"
                    : "bg-white/[0.02] border-white/10 text-white/50 hover:text-white/80"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <label className="text-[11px] text-white/40 font-mono">
              channel
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value as Platform | "")}
                className="ml-2 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-xs"
              >
                <option value="">all</option>
                {knownPlatforms.map((p) => (
                  <option key={p} value={p}>
                    {PLATFORM_BY_ID[p]?.label ?? p}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={() => void refresh()}
              className="text-xs text-white/50 hover:text-white inline-flex items-center gap-1"
            >
              <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>
        </div>
      </section>

      {error && (
        <div className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="text-sm text-white/40 text-center py-12 inline-flex items-center gap-2 justify-center w-full">
          <Loader2 size={14} className="animate-spin" />
          Loading...
        </div>
      ) : empty ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] px-6 py-12 text-center">
          <BarChart3 size={20} className="mx-auto mb-3 text-white/30" />
          <p className="text-sm text-white/60 mb-1">No engagement recorded in this window.</p>
          <p className="text-xs text-white/40">
            Post a draft, then turn on the outcome puller in the extension popup — metrics land here
            after its next pass.
          </p>
        </div>
      ) : data ? (
        <>
          <section className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            <StatTile label="drafts with engagement" value={data.draft_count} />
            {kinds.slice(0, 3).map((k) => (
              <StatTile key={k} label={k} value={data.totals[k] ?? 0} />
            ))}
          </section>

          <section className="rounded-xl border border-white/10 bg-white/[0.03] p-5 mb-6">
            <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
              <h2 className="text-sm font-semibold">
                {metric} per {data.window.bucket}
              </h2>
              <div className="flex items-center gap-1 text-[11px] font-mono" role="group" aria-label="Metric">
                {kinds.map((k) => (
                  <button
                    key={k}
                    onClick={() => setMetric(k)}
                    aria-pressed={k === metric}
                    className={`rounded-md border px-2 py-0.5 transition-colors ${
                      k === metric
                        ? "bg-violet-500/15 border-violet-400/40 text-violet-100"
                        : "bg-white/[0.02] border-white/10 text-white/50 hover:text-white/80"
                    }`}
                  >
                    {k}
                  </button>
                ))}
              </div>
            </div>
            <BarChart series={data.timeseries} metric={metric} bucket={data.window.bucket} />
          </section>

          <section className="rounded-xl border border-white/10 bg-white/[0.03] overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Engagement per channel</caption>
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-white/40 font-mono border-b border-white/10">
                  <th scope="col" className="text-left px-4 py-2.5 font-normal">channel</th>
                  <th scope="col" className="text-right px-3 py-2.5 font-normal">drafts</th>
                  {kinds.map((k) => (
                    <th key={k} scope="col" className="text-right px-3 py-2.5 font-normal">
                      {k}
                    </th>
                  ))}
                  <th scope="col" className="text-right px-3 py-2.5 font-normal">engagement</th>
                  <th scope="col" className="text-left px-4 py-2.5 font-normal">best post</th>
                </tr>
              </thead>
              <tbody>
                {data.channels.map((c) => {
                  const meta = PLATFORM_BY_ID[c.platform];
                  const Icon = meta?.Icon;
                  return (
                    <tr key={c.platform} className="border-b border-white/[0.06] last:border-0">
                      <th scope="row" className="text-left px-4 py-2.5 font-medium">
                        <span className="inline-flex items-center gap-2">
                          {Icon && <Icon size={13} className="text-white/60" aria-hidden />}
                          {meta?.label ?? c.platform}
                        </span>
                      </th>
                      <td className="text-right px-3 py-2.5 tabular-nums text-white/70">{c.draft_count}</td>
                      {kinds.map((k) => (
                        <td key={k} className="text-right px-3 py-2.5 tabular-nums text-white/80">
                          {fmt(c.totals[k] ?? 0)}
                          {c.per_draft[k] !== undefined && c.draft_count > 1 && (
                            <span className="block text-[10px] text-white/40">
                              {fmt(c.per_draft[k])}/draft
                            </span>
                          )}
                        </td>
                      ))}
                      <td className="text-right px-3 py-2.5 tabular-nums font-semibold">{fmt(c.engagement)}</td>
                      <td className="px-4 py-2.5 text-xs text-white/60">
                        {c.top_draft ? (
                          c.top_draft.post_url ? (
                            <a
                              href={c.top_draft.post_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 hover:text-white underline-offset-2 hover:underline"
                            >
                              {fmt(c.top_draft.metric_value)} {c.top_draft.metric_kind}
                              <ExternalLink size={10} />
                            </a>
                          ) : (
                            <span>
                              {fmt(c.top_draft.metric_value)} {c.top_draft.metric_kind}
                            </span>
                          )
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </main>
  );
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <p className="text-[11px] uppercase tracking-wider text-white/40 font-mono">{label}</p>
      <p className="text-2xl font-semibold tabular-nums mt-1">{fmt(value)}</p>
    </div>
  );
}

const CHART_H = 160;

function BarChart({
  series,
  metric,
  bucket,
}: {
  series: EngagementAnalytics["timeseries"];
  metric: string;
  bucket: AnalyticsBucket;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const values = series.map((b) => b.totals[metric] ?? 0);
  const max = Math.max(1, ...values);
  const label = (iso: string) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    });
  // ~6 evenly spaced x-axis labels, always including the last bucket.
  const every = Math.max(1, Math.ceil(series.length / 6));

  return (
    <div className="relative" onMouseLeave={() => setHover(null)}>
      <div className="flex items-end gap-[2px] border-b border-white/15" style={{ height: CHART_H }}>
        {series.map((b, i) => {
          const v = values[i];
          const h = v === 0 ? 0 : Math.max(3, (v / max) * (CHART_H - 8));
          return (
            <div
              key={b.bucket_start}
              className="relative flex-1 h-full flex items-end cursor-default"
              onMouseEnter={() => setHover(i)}
              role="img"
              aria-label={`${bucket} of ${label(b.bucket_start)}: ${v} ${metric}`}
            >
              <div
                className={`w-full rounded-t-[4px] transition-colors ${
                  hover === i ? "bg-violet-300" : "bg-violet-400/80"
                }`}
                style={{ height: h }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex gap-[2px] mt-1.5 text-[10px] text-white/40 font-mono">
        {series.map((b, i) => (
          <div key={b.bucket_start} className="flex-1 text-center whitespace-nowrap overflow-visible">
            {i % every === 0 || i === series.length - 1 ? label(b.bucket_start) : ""}
          </div>
        ))}
      </div>
      <p className="absolute top-0 left-0 text-[10px] text-white/30 font-mono">{fmt(max)}</p>
      {hover !== null && (
        <div
          className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full rounded-md border border-white/15 bg-black/90 px-2 py-1 text-[11px] whitespace-nowrap"
          style={{ left: `${((hover + 0.5) / series.length) * 100}%` }}
        >
          <span className="text-white/50">
            {bucket === "week" ? "week of " : ""}
            {label(series[hover].bucket_start)}
          </span>{" "}
          <span className="font-semibold tabular-nums">
            {fmt(values[hover])} {metric}
          </span>
        </div>
      )}
    </div>
  );
}
