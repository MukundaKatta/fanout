"use client";

/**
 * Operator history — full timeline of autonomous draft cycles.
 *
 * Each OperatorRun row carries the experiment the operator picked
 * (cited snippet ids), the drafts it produced (draft_ids), and a one-line
 * notes summary. This page is the "what happened?" companion to the
 * Autonomous draft cycles panel on /research, surfacing the audit trail
 * without forcing the user to hit /operator/runs/{id} by hand.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  Sparkles,
  XCircle,
} from "lucide-react";
import { api, OperatorRun, OperatorRunStatus } from "@/lib/api";

type StatusFilter = "all" | OperatorRunStatus;

const STATUS_META: Record<OperatorRunStatus, { label: string; tone: string; icon: typeof CheckCircle2 }> = {
  ok: {
    label: "ok",
    tone: "bg-emerald-500/15 border-emerald-400/40 text-emerald-200",
    icon: CheckCircle2,
  },
  failed: {
    label: "failed",
    tone: "bg-rose-500/15 border-rose-400/40 text-rose-200",
    icon: XCircle,
  },
  pending: {
    label: "pending",
    tone: "bg-amber-500/15 border-amber-400/40 text-amber-200",
    icon: Clock,
  },
};

export default function OperatorPage() {
  const [runs, setRuns] = useState<OperatorRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [limit, setLimit] = useState(20);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setRuns(await api.operator.list(limit));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRuns([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit]);

  const filtered = useMemo(
    () => (filter === "all" ? runs : runs.filter((r) => r.status === filter)),
    [runs, filter]
  );

  const counts = useMemo(() => {
    const ok = runs.filter((r) => r.status === "ok").length;
    const failed = runs.filter((r) => r.status === "failed").length;
    const pending = runs.filter((r) => r.status === "pending").length;
    return { all: runs.length, ok, failed, pending };
  }, [runs]);

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
        <p className="text-[11px] uppercase tracking-wider text-emerald-300/80 font-mono mb-1">
          OPERATOR HISTORY
        </p>
        <h1 className="text-3xl font-bold tracking-tight mb-2">
          Every autonomous cycle, replayable
        </h1>
        <p className="text-sm text-white/60 max-w-3xl">
          One row per <code className="text-white/70 font-mono">operator.run</code>{" "}
          call. Snapshots the experiment the operator picked, the drafts it
          produced, and whether leaderboard weighting actually influenced the
          picks. Pair with{" "}
          <Link href="/research" className="underline hover:text-white">
            the research page
          </Link>{" "}
          to spot which sources are feeding the operator's best cycles.
        </p>
      </div>

      <section className="rounded-xl border border-white/10 bg-white/[0.03] p-5 mb-6">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-1 text-xs font-mono">
            <FilterPill
              label={`all · ${counts.all}`}
              active={filter === "all"}
              onClick={() => setFilter("all")}
            />
            <FilterPill
              label={`ok · ${counts.ok}`}
              active={filter === "ok"}
              onClick={() => setFilter("ok")}
              accent="emerald"
            />
            <FilterPill
              label={`failed · ${counts.failed}`}
              active={filter === "failed"}
              onClick={() => setFilter("failed")}
              accent="rose"
            />
            {counts.pending > 0 && (
              <FilterPill
                label={`pending · ${counts.pending}`}
                active={filter === "pending"}
                onClick={() => setFilter("pending")}
                accent="amber"
              />
            )}
          </div>
          <div className="flex items-center gap-2">
            <label className="text-[11px] text-white/40 font-mono">
              show
              <select
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="ml-2 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-xs"
              >
                <option value={20}>last 20</option>
                <option value={50}>last 50</option>
                <option value={100}>last 100</option>
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

      {loading && runs.length === 0 ? (
        <div className="text-sm text-white/40 text-center py-12 inline-flex items-center gap-2 justify-center w-full">
          <Loader2 size={14} className="animate-spin" />
          Loading...
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] px-6 py-12 text-center">
          <Sparkles size={20} className="mx-auto mb-3 text-white/30" />
          <p className="text-sm text-white/60 mb-1">
            {runs.length === 0
              ? "No autonomous cycles yet."
              : `No cycles with status '${filter}'.`}
          </p>
          <p className="text-xs text-white/40">
            {runs.length === 0 ? (
              <>
                Create an autonomous cycle on{" "}
                <Link href="/research" className="underline hover:text-white">
                  the research page
                </Link>{" "}
                to start the loop.
              </>
            ) : (
              "Try switching the filter above."
            )}
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {filtered.map((run) => (
            <OperatorRunRow key={run.id} run={run} />
          ))}
        </ul>
      )}
    </main>
  );
}

function FilterPill({
  label,
  active,
  onClick,
  accent,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  accent?: "emerald" | "rose" | "amber";
}) {
  const accentClasses =
    accent === "emerald"
      ? "data-active:bg-emerald-500/15 data-active:border-emerald-400/40 data-active:text-emerald-100"
      : accent === "rose"
      ? "data-active:bg-rose-500/15 data-active:border-rose-400/40 data-active:text-rose-100"
      : accent === "amber"
      ? "data-active:bg-amber-500/15 data-active:border-amber-400/40 data-active:text-amber-100"
      : "data-active:bg-white/10 data-active:border-white/30 data-active:text-white";

  return (
    <button
      data-active={active ? "true" : undefined}
      onClick={onClick}
      className={`rounded-md border px-2.5 py-1 transition-colors ${
        active
          ? accent === "emerald"
            ? "bg-emerald-500/15 border-emerald-400/40 text-emerald-100"
            : accent === "rose"
            ? "bg-rose-500/15 border-rose-400/40 text-rose-100"
            : accent === "amber"
            ? "bg-amber-500/15 border-amber-400/40 text-amber-100"
            : "bg-white/10 border-white/30 text-white"
          : "bg-white/[0.02] border-white/10 text-white/50 hover:text-white/80"
      } ${accentClasses}`}
    >
      {label}
    </button>
  );
}

function OperatorRunRow({ run }: { run: OperatorRun }) {
  const meta = STATUS_META[run.status];
  const Icon = meta.icon;

  return (
    <li className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3.5">
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-mono uppercase ${meta.tone}`}>
          <Icon size={10} />
          {meta.label}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3 flex-wrap text-[11px] text-white/40 font-mono">
            <time dateTime={run.started_at}>
              {new Date(run.started_at).toLocaleString()}
            </time>
            <span>·</span>
            <span>{run.platforms.length} platform{run.platforms.length === 1 ? "" : "s"}</span>
            <span>·</span>
            <span>{run.draft_ids.length} draft{run.draft_ids.length === 1 ? "" : "s"}</span>
            <span>·</span>
            <span>{run.cited_snippet_ids.length} snippet{run.cited_snippet_ids.length === 1 ? "" : "s"}</span>
            {run.weight_by_leaderboard && (
              <>
                <span>·</span>
                <span className="text-emerald-300/80">leaderboard-weighted ({run.leaderboard_metric})</span>
              </>
            )}
          </div>
          <p className="mt-1.5 text-sm text-white/85 italic line-clamp-2">{run.product}</p>
          <div className="mt-1.5 flex items-center gap-2 flex-wrap">
            {run.platforms.map((p) => (
              <span
                key={p}
                className="rounded bg-white/[0.04] border border-white/10 px-1.5 py-0.5 text-[10px] font-mono text-white/60"
              >
                {p}
              </span>
            ))}
          </div>
          {run.error && (
            <p className="mt-2 text-xs text-rose-300/80 font-mono">
              error: {run.error}
            </p>
          )}
          {run.notes && (
            <p className="mt-2 text-[11px] text-white/45 leading-relaxed">
              {run.notes}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}
