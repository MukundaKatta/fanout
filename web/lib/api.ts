"use client";

import { supabase, supabaseEnabled } from "./supabase";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function authHeader(): Promise<Record<string, string>> {
  if (!supabaseEnabled || !supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) ?? {}),
    ...(await authHeader()),
  };
  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  generate: (product: string, platforms: string[], opts?: { useResearch?: boolean }) =>
    request<{ plan: unknown; drafts: Draft[]; research_used?: number }>("/generate", {
      method: "POST",
      body: JSON.stringify({
        product,
        platforms,
        use_research: opts?.useResearch ?? false,
      }),
    }),
  variations: (
    product: string,
    platform: Platform,
    count = 5,
    opts?: { useResearch?: boolean },
  ) =>
    request<{ drafts: Draft[]; research_used?: number }>("/variations", {
      method: "POST",
      body: JSON.stringify({
        product,
        platform,
        count,
        use_research: opts?.useResearch ?? false,
      }),
    }),
  list: () => request<Draft[]>("/drafts"),
  edit: (id: string, content: string) =>
    request<Draft>(`/drafts/${id}?content=${encodeURIComponent(content)}`, {
      method: "PATCH",
    }),
  queue: (id: string) => request<Draft>(`/drafts/${id}/queue`, { method: "POST" }),
  queueBulk: (ids: string[]) =>
    request<{ queued: Draft[] }>("/queue-bulk", {
      method: "POST",
      body: JSON.stringify({ draft_ids: ids }),
    }),
  schedule: (id: string, isoDate: string) =>
    request<Draft>(`/drafts/${id}/schedule`, {
      method: "POST",
      body: JSON.stringify({ scheduled_at: isoDate }),
    }),
  cancelSchedule: (id: string) =>
    request<Draft>(`/drafts/${id}/schedule`, { method: "DELETE" }),
  me: () => request<{ user_id: string }>("/me"),

  // --- research loop ---------------------------------------------------------
  research: {
    run: (input: {
      queries?: string[];
      rss_feeds?: string[];
      sources?: ResearchSource[];
      per_source_limit?: number;
    }) =>
      request<{ fetched: number; saved: ResearchSnippet[] }>("/research", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    list: (params?: { source?: ResearchSource; only_unused?: boolean; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.source) qs.set("source", params.source);
      if (params?.only_unused) qs.set("only_unused", "true");
      if (params?.limit != null) qs.set("limit", String(params.limit));
      const tail = qs.toString();
      return request<ResearchSnippet[]>(`/research${tail ? `?${tail}` : ""}`);
    },
    suggest: (product: string, count = 5) =>
      request<{ queries: string[] }>("/research/suggest", {
        method: "POST",
        body: JSON.stringify({ product, count }),
      }),

    subscriptions: {
      list: () => request<ResearchSubscription[]>("/research/subscriptions"),
      create: (input: {
        name: string;
        queries?: string[];
        rss_feeds?: string[];
        sources?: ResearchSource[];
        interval_hours?: number;
        active?: boolean;
      }) =>
        request<ResearchSubscription>("/research/subscriptions", {
          method: "POST",
          body: JSON.stringify(input),
        }),
      update: (id: string, patch: Partial<{
        name: string;
        queries: string[];
        rss_feeds: string[];
        sources: ResearchSource[];
        interval_hours: number;
        active: boolean;
      }>) =>
        request<ResearchSubscription>(`/research/subscriptions/${id}`, {
          method: "PATCH",
          body: JSON.stringify(patch),
        }),
      remove: (id: string) =>
        request<{ deleted: string }>(`/research/subscriptions/${id}`, {
          method: "DELETE",
        }),
    },

    tick: () =>
      request<{ ran: { id: string; name: string; fetched: number; error: string | null }[] }>(
        "/research/tick",
        { method: "POST" }
      ),
  },
};

export type Status = "pending" | "queued" | "scheduled" | "posting" | "posted" | "failed";
export type Platform =
  | "linkedin"
  | "x"
  | "threads"
  | "bluesky"
  | "mastodon"
  | "instagram"
  | "reddit"
  | "hackernews"
  | "producthunt"
  | "medium"
  | "devto"
  | "email"
  | "telegram"
  | "discord"
  | "slack";

export type Draft = {
  id: string;
  platform: Platform;
  content: string;
  feedback?: string | null; // for variations, holds the angle name
  status: Status;
  scheduled_at: string | null;
  post_url?: string | null;
  error?: string | null;
  created_at: string;
};

export type ResearchSource = "hn" | "devto" | "reddit" | "rss";

export type ResearchSnippet = {
  id: string;
  source: ResearchSource;
  query: string | null;
  url: string;
  title: string;
  snippet: string | null;
  author: string | null;
  score: number;
  published_at: string | null;
  used_in_draft_id: string | null;
  created_at: string;
};

export type ResearchSubscription = {
  id: string;
  user_id: string;
  name: string;
  queries: string[];
  rss_feeds: string[];
  sources: ResearchSource[];
  interval_hours: number;
  active: boolean;
  last_run_at: string | null;
  last_fetched_count: number | null;
  last_error: string | null;
  created_at: string;
};
