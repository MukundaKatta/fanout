// Regression tests for the background worker's polling loop. Loads
// src/background.js into a vm sandbox with a stub `chrome` global so it runs
// under plain `node` (no browser, no deps).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(resolve(here, "../src/background.js"), "utf8");

function event() {
  const listeners = new Set();
  return {
    addListener: (fn) => listeners.add(fn),
    removeListener: (fn) => listeners.delete(fn),
    listeners,
  };
}

function load({ fetch, tabStatus = "complete" }) {
  const chrome = {
    storage: { local: { get: async () => ({ apiUrl: "http://api.test", enabled: true }) } },
    runtime: { onInstalled: event(), onStartup: event(), onMessage: event() },
    alarms: { create: () => {}, onAlarm: event() },
    tabs: {
      onUpdated: event(),
      get: async (id) => ({ id, status: tabStatus }),
      query: async () => [],
      create: async ({ url }) => ({ id: 1, url }),
      sendMessage: async () => ({ ok: true }),
    },
    scripting: { executeScript: async () => [] },
  };
  const ctx = vm.createContext({ chrome, fetch, console, setTimeout, clearTimeout, Promise });
  vm.runInContext(src, ctx);
  return ctx;
}

let failures = 0;
function assert(cond, label, ctx) {
  if (!cond) {
    failures++;
    console.error("FAIL:", label, ctx ?? "");
  }
}

// --- poll() is single-flight -------------------------------------------------
{
  let queueCalls = 0;
  let release;
  const gate = new Promise((r) => (release = r));
  const fetch = async (url) => {
    if (url.endsWith("/queue")) {
      queueCalls++;
      await gate; // hold the first cycle open
      return { ok: true, json: async () => [] };
    }
    return { ok: true, json: async () => ({}) };
  };
  const ctx = load({ fetch });
  const a = ctx.poll();
  const b = ctx.poll(); // alarm fires while "Poll now" is still running
  await new Promise((r) => setTimeout(r, 10));
  assert(queueCalls === 1, "overlapping poll() calls share one cycle", { queueCalls });
  release();
  await Promise.all([a, b]);
  await ctx.poll(); // a fresh cycle runs once the previous one finished
  assert(queueCalls === 2, "poll() runs again after the in-flight cycle ends", { queueCalls });
}

// --- waitForTabLoad doesn't stall on an already-loaded tab -------------------
{
  const ctx = load({ fetch: async () => ({ ok: false }) });
  const t0 = Date.now();
  await ctx.waitForTabLoad(1, { timeout: 2000 });
  const elapsed = Date.now() - t0;
  assert(elapsed < 500, "already-complete tab resolves immediately", { elapsed });
  assert(ctx.chrome.tabs.onUpdated.listeners.size === 0, "listener removed", {});
}

// --- ...but still waits for a tab that is loading ----------------------------
{
  const ctx = load({ fetch: async () => ({ ok: false }), tabStatus: "loading" });
  let resolved = false;
  const p = ctx.waitForTabLoad(7, { timeout: 2000 }).then(() => (resolved = true));
  await new Promise((r) => setTimeout(r, 30));
  assert(!resolved, "loading tab is still awaited", {});
  for (const fn of ctx.chrome.tabs.onUpdated.listeners) fn(7, { status: "complete" });
  await p;
  assert(resolved, "resolves on the complete event", {});
}

if (failures > 0) {
  console.error(`${failures} background-worker assertion(s) failed`);
  process.exit(1);
}
console.log("OK — background worker polling tests pass");
