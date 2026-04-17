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
  generate: (product: string, platforms: string[]) =>
    request<{ plan: unknown; drafts: Draft[] }>("/generate", {
      method: "POST",
      body: JSON.stringify({ product, platforms }),
    }),
  variations: (product: string, platform: Platform, count = 5) =>
    request<{ drafts: Draft[] }>("/variations", {
      method: "POST",
      body: JSON.stringify({ product, platform, count }),
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
