import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Supabase state is mutated per-test via this hoisted holder so we can cover
// both the dev-mode (no auth) and signed-in branches of authHeader().
const sb = vi.hoisted(() => ({
  enabled: false,
  token: null as string | null,
}));

vi.mock("../supabase", () => ({
  get supabaseEnabled() {
    return sb.enabled;
  },
  get supabase() {
    return sb.enabled
      ? {
          auth: {
            getSession: async () => ({
              data: { session: sb.token ? { access_token: sb.token } : null },
            }),
          },
        }
      : null;
  },
}));

import { api } from "../api";

type Call = { url: string; init: RequestInit };
let calls: Call[];
let nextResponse: { ok: boolean; status: number; body: unknown; text?: string };

beforeEach(() => {
  sb.enabled = false;
  sb.token = null;
  calls = [];
  nextResponse = { ok: true, status: 200, body: { ok: true } };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      const r = nextResponse;
      return {
        ok: r.ok,
        status: r.status,
        json: async () => r.body,
        text: async () => r.text ?? JSON.stringify(r.body),
      };
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const last = () => calls[calls.length - 1];
const headers = () => last().init.headers as Record<string, string>;
const body = () => JSON.parse(last().init.body as string);

describe("request()", () => {
  it("targets the default API base and sends JSON content-type", async () => {
    await expect(api.me()).resolves.toEqual({ ok: true });
    expect(last().url).toBe("http://localhost:8000/me");
    expect(headers()["Content-Type"]).toBe("application/json");
    expect(headers().Authorization).toBeUndefined();
  });

  it("throws with status and body text on non-2xx", async () => {
    nextResponse = { ok: false, status: 404, body: null, text: '{"detail":"Not found"}' };
    await expect(api.me()).rejects.toThrow('404 {"detail":"Not found"}');
  });

  it("adds a bearer token when signed in via Supabase", async () => {
    sb.enabled = true;
    sb.token = "jwt-123";
    await api.list();
    expect(headers().Authorization).toBe("Bearer jwt-123");
  });

  it("omits Authorization when Supabase has no session", async () => {
    sb.enabled = true;
    sb.token = null;
    await api.list();
    expect(headers().Authorization).toBeUndefined();
  });
});

describe("draft endpoints", () => {
  it("generate defaults use_research to false", async () => {
    await api.generate("prod", ["x"]);
    expect(last().url).toMatch(/\/generate$/);
    expect(last().init.method).toBe("POST");
    expect(body()).toEqual({ product: "prod", platforms: ["x"], use_research: false });
    await api.generate("prod", ["x"], { useResearch: true });
    expect(body().use_research).toBe(true);
  });

  it("variations sends platform + count", async () => {
    await api.variations("prod", "linkedin");
    expect(body()).toEqual({ product: "prod", platform: "linkedin", count: 5, use_research: false });
    await api.variations("prod", "x", 3, { useResearch: true });
    expect(body()).toEqual({ product: "prod", platform: "x", count: 3, use_research: true });
  });

  it("edit URL-encodes content into the query string", async () => {
    await api.edit("d1", "a & b?c=#");
    expect(last().url).toBe("http://localhost:8000/drafts/d1?content=a%20%26%20b%3Fc%3D%23");
    expect(last().init.method).toBe("PATCH");
  });

  it("queue / queueBulk / schedule / cancelSchedule / citations", async () => {
    await api.queue("d1");
    expect([last().url, last().init.method]).toEqual(["http://localhost:8000/drafts/d1/queue", "POST"]);
    await api.queueBulk(["a", "b"]);
    expect(body()).toEqual({ draft_ids: ["a", "b"] });
    await api.schedule("d1", "2026-01-01T00:00:00Z");
    expect(body()).toEqual({ scheduled_at: "2026-01-01T00:00:00Z" });
    await api.cancelSchedule("d1");
    expect([last().url, last().init.method]).toEqual(["http://localhost:8000/drafts/d1/schedule", "DELETE"]);
    await api.citations("d1");
    expect(last().url).toBe("http://localhost:8000/drafts/d1/citations");
  });
});

describe("research endpoints", () => {
  it("list builds the query string only from provided params", async () => {
    await api.research.list();
    expect(last().url).toBe("http://localhost:8000/research");
    await api.research.list({ source: "hn", only_unused: true, limit: 0 });
    expect(last().url).toBe("http://localhost:8000/research?source=hn&only_unused=true&limit=0");
    await api.research.list({ only_unused: false });
    expect(last().url).toBe("http://localhost:8000/research");
  });

  it("run / suggest / tick", async () => {
    await api.research.run({ queries: ["agents"] });
    expect(body()).toEqual({ queries: ["agents"] });
    await api.research.suggest("prod");
    expect(body()).toEqual({ product: "prod", count: 5 });
    await api.research.tick();
    expect([last().url, last().init.method]).toEqual(["http://localhost:8000/research/tick", "POST"]);
  });

  it("subscriptions CRUD hits the right verbs", async () => {
    await api.research.subscriptions.list();
    expect(last().init.method).toBeUndefined();
    await api.research.subscriptions.create({ name: "n", queries: ["q"] });
    expect(last().init.method).toBe("POST");
    await api.research.subscriptions.update("s1", { active: false });
    expect([last().url, last().init.method, body()]).toEqual([
      "http://localhost:8000/research/subscriptions/s1",
      "PATCH",
      { active: false },
    ]);
    await api.research.subscriptions.remove("s1");
    expect(last().init.method).toBe("DELETE");
  });

  it("leaderboard encodes metric and defaults", async () => {
    await api.research.leaderboard();
    expect(last().url).toBe("http://localhost:8000/research/sources/leaderboard?metric=likes&limit=10");
    await api.research.leaderboard("views", 3);
    expect(last().url).toBe("http://localhost:8000/research/sources/leaderboard?metric=views&limit=3");
  });
});

describe("outcomes + operator endpoints", () => {
  it("outcomes record/list", async () => {
    await api.outcomes.record("d1", { metric_kind: "likes", metric_value: 4 });
    expect([last().url, body()]).toEqual([
      "http://localhost:8000/drafts/d1/outcomes",
      { metric_kind: "likes", metric_value: 4 },
    ]);
    await api.outcomes.list("d1");
    expect(last().url).toBe("http://localhost:8000/drafts/d1/outcomes");
  });

  it("operator run/list/get/tick", async () => {
    await api.operator.run({ product: "prod" });
    expect([last().url, body()]).toEqual(["http://localhost:8000/operator/run", { product: "prod" }]);
    await api.operator.list();
    expect(last().url).toBe("http://localhost:8000/operator/runs?limit=20");
    await api.operator.get("r1");
    expect(last().url).toBe("http://localhost:8000/operator/runs/r1");
    await api.operator.tick();
    expect(last().init.method).toBe("POST");
  });

  it("operator subscriptions CRUD", async () => {
    await api.operator.subscriptions.list();
    expect(last().url).toBe("http://localhost:8000/operator/subscriptions");
    await api.operator.subscriptions.create({ name: "n", product: "p" });
    expect(last().init.method).toBe("POST");
    await api.operator.subscriptions.update("o1", { snippet_limit: 3 });
    expect([last().url, last().init.method, body()]).toEqual([
      "http://localhost:8000/operator/subscriptions/o1",
      "PATCH",
      { snippet_limit: 3 },
    ]);
    await api.operator.subscriptions.remove("o1");
    expect(last().init.method).toBe("DELETE");
  });
});
