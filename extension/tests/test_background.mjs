// Tests for the MV3 background worker (src/background.js).
//
// background.js is a classic (non-module) script that talks to `chrome.*`
// and `fetch`. We load it into a fresh node:vm context with stubbed globals
// so its top-level function declarations become context properties we can
// call directly. No deps beyond node's built-in test runner.
//
// Run: node --test tests/test_background.mjs   (or: node tests/test_background.mjs)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(resolve(here, "../src/background.js"), "utf8");

function makeEvent() {
  const listeners = [];
  return {
    listeners,
    addListener: (fn) => listeners.push(fn),
    removeListener: (fn) => {
      const i = listeners.indexOf(fn);
      if (i >= 0) listeners.splice(i, 1);
    },
  };
}

/**
 * Build a sandbox. `storage` seeds chrome.storage.local, `routes` maps
 * "METHOD path" → response body (or a function returning one / throwing).
 */
function load({ storage = {}, routes = {}, sendMessage, existingTabs = [], executeScript } = {}) {
  const fetchCalls = [];
  const tabsCreated = [];
  const tabsRemoved = [];
  const alarmsCreated = [];
  let nextTabId = 100;

  const onUpdated = makeEvent();
  const chrome = {
    storage: {
      local: {
        get: async (keys) => Object.fromEntries(keys.filter((k) => k in storage).map((k) => [k, storage[k]])),
      },
    },
    tabs: {
      query: async () => existingTabs,
      create: async ({ url, active }) => {
        const tab = { id: nextTabId++, url, active };
        tabsCreated.push(tab);
        return tab;
      },
      remove: async (id) => {
        tabsRemoved.push(id);
      },
      sendMessage: sendMessage ?? (async () => ({ ok: true, postUrl: "https://posted/1" })),
      onUpdated,
    },
    scripting: {
      executeScript: executeScript ?? (async () => [{ result: true }]),
    },
    alarms: {
      create: (name, opts) => alarmsCreated.push({ name, ...opts }),
      onAlarm: makeEvent(),
    },
    runtime: {
      onInstalled: makeEvent(),
      onStartup: makeEvent(),
      onMessage: makeEvent(),
    },
  };

  const fetch = async (url, init = {}) => {
    const method = init.method ?? "GET";
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    fetchCalls.push({ url, method, path, headers: init.headers ?? {}, body: init.body ? JSON.parse(init.body) : undefined });
    const key = `${method} ${path}`;
    let handler = routes[key];
    if (handler === undefined) handler = { status: 200, body: {} };
    if (typeof handler === "function") handler = await handler();
    const { status = 200, body = {} } = handler;
    return { ok: status >= 200 && status < 300, status, json: async () => body };
  };

  const context = vm.createContext({
    chrome,
    fetch,
    console: { warn: () => {}, log: () => {}, error: () => {} },
    // Collapse all delays (SPA settle, tab-load timeout) to the next tick.
    setTimeout: (fn) => setImmediate(fn),
    encodeURIComponent,
    JSON,
    Promise,
    Number,
    Object,
    String,
  });
  vm.runInContext(src, context, { filename: "background.js" });
  return { ctx: context, chrome, fetchCalls, tabsCreated, tabsRemoved, alarmsCreated };
}

// vm-context objects live in another realm; deepStrictEqual needs plain copies.
const plain = (v) => JSON.parse(JSON.stringify(v));

const posted = (s) => s.fetchCalls.filter((c) => c.path === "/posted").map((c) => c.body);

// --- config ------------------------------------------------------------------

test("getConfig applies defaults", async () => {
  const s = load();
  const cfg = await s.ctx.getConfig();
  assert.equal(cfg.apiUrl, "http://localhost:8000");
  assert.equal(cfg.enabled, true);
  assert.equal(cfg.jwt, "");
  assert.equal(cfg.outcomesEnabled, false);
  assert.equal(cfg.outcomesIntervalMinutes, 60);
});

test("getConfig honours stored values and rejects bad interval", async () => {
  const s = load({
    storage: { apiUrl: "https://api.x", enabled: false, jwt: "t", outcomesEnabled: true, outcomesIntervalMinutes: "15" },
  });
  const cfg = await s.ctx.getConfig();
  assert.deepEqual({ ...cfg }, {
    apiUrl: "https://api.x",
    enabled: false,
    jwt: "t",
    outcomesEnabled: true,
    outcomesIntervalMinutes: 15,
  });
  const bad = load({ storage: { outcomesIntervalMinutes: -3 } });
  assert.equal((await bad.ctx.getConfig()).outcomesIntervalMinutes, 60);
});

test("authHeaders only adds Authorization when a jwt is set", () => {
  const s = load();
  assert.deepEqual({ ...s.ctx.authHeaders("") }, {});
  assert.deepEqual({ ...s.ctx.authHeaders("abc") }, { Authorization: "Bearer abc" });
});

// --- text splitters ----------------------------------------------------------

test("splitEmail strips SUBJECT: prefix", () => {
  const s = load();
  const out = s.ctx.splitEmail("SUBJECT: Hello there\n\nBody line 1\nBody line 2");
  assert.equal(out.subject, "Hello there");
  assert.equal(out.body, "Body line 1\nBody line 2");
  assert.equal(s.ctx.splitEmail("Just a subject").body, "");
});

test("splitTitleBody strips TITLE: prefix case-insensitively", () => {
  const s = load();
  const out = s.ctx.splitTitleBody("title: Show HN\n\nthe body");
  assert.equal(out.title, "Show HN");
  assert.equal(out.body, "the body");
});

// --- dispatch ----------------------------------------------------------------

test("dispatch: unsupported platform reports an error", async () => {
  const s = load();
  await s.ctx.dispatch({ platform: "myspace", draft_id: "d1", content: "c" });
  assert.deepEqual(posted(s), [{ draft_id: "d1", post_url: null, error: "Unsupported platform: myspace" }]);
});

test("dispatch: email opens a mailto composer and is not an error", async () => {
  const s = load();
  await s.ctx.dispatch({ platform: "email", draft_id: "d2", content: "SUBJECT: Hi & bye\n\nBody?" });
  assert.equal(s.tabsCreated.length, 1);
  assert.equal(s.tabsCreated[0].url, "mailto:?subject=Hi%20%26%20bye&body=Body%3F");
  assert.deepEqual(posted(s), [{ draft_id: "d2", post_url: null, error: null }]);
});

test("dispatch: copy & open platforms open compose page and copy content", async () => {
  const scripts = [];
  const s = load({ executeScript: async (opts) => (scripts.push(plain(opts)), [{ result: true }]) });
  await s.ctx.dispatch({ platform: "hackernews", draft_id: "d3", content: "Show HN: x" });
  assert.equal(s.tabsCreated[0].url, "https://news.ycombinator.com/submit");
  assert.deepEqual(scripts[0].args, ["Show HN: x"]);
  assert.deepEqual(posted(s), [{ draft_id: "d3", post_url: null, error: null }]);
});

test("dispatch: clipboard failure on copy & open is still not an error", async () => {
  const s = load({ executeScript: async () => { throw new Error("no perms"); } });
  await s.ctx.dispatch({ platform: "devto", draft_id: "d4", content: "post" });
  assert.deepEqual(posted(s), [{ draft_id: "d4", post_url: null, error: null }]);
});

test("dispatch: reddit prefills title in URL and copies body", async () => {
  const scripts = [];
  const s = load({ executeScript: async (opts) => (scripts.push(plain(opts)), [{ result: true }]) });
  await s.ctx.dispatch({ platform: "reddit", draft_id: "d5", content: "TITLE: My thing\n\nbody text" });
  assert.equal(s.tabsCreated[0].url, "https://www.reddit.com/submit?title=My%20thing");
  assert.deepEqual(scripts[0].args, ["body text"]);
  assert.equal(posted(s)[0].error, null);
});

test("dispatch: auto-post reuses an existing tab and reports the post URL", async () => {
  const messages = [];
  const s = load({
    existingTabs: [{ id: 7 }],
    sendMessage: async (tabId, msg) => (messages.push(plain({ tabId, msg })), { ok: true, postUrl: "https://x.com/s/1" }),
  });
  await s.ctx.dispatch({ platform: "x", draft_id: "d6", content: "hello" });
  assert.equal(s.tabsCreated.length, 0);
  assert.deepEqual(messages, [{ tabId: 7, msg: { type: "fanout:post", platform: "x", draft_id: "d6", content: "hello" } }]);
  assert.deepEqual(posted(s), [{ draft_id: "d6", post_url: "https://x.com/s/1", error: null }]);
});

test("dispatch: auto-post opens a background tab when none exists", async () => {
  const s = load();
  await s.ctx.dispatch({ platform: "bluesky", draft_id: "d7", content: "hi" });
  assert.equal(s.tabsCreated[0].url, "https://bsky.app/");
  assert.equal(s.tabsCreated[0].active, false);
});

test("dispatch: content-script failure is reported as error", async () => {
  const s = load({ sendMessage: async () => ({ ok: false, error: "composer not found" }) });
  await s.ctx.dispatch({ platform: "linkedin", draft_id: "d8", content: "hi" });
  assert.equal(posted(s)[0].error, "composer not found");
});

test("dispatch: missing content-script response falls back to 'unknown error'", async () => {
  const s = load({ sendMessage: async () => undefined });
  await s.ctx.dispatch({ platform: "threads", draft_id: "d9", content: "hi" });
  assert.equal(posted(s)[0].error, "unknown error");
});

test("dispatch: thrown exception is reported as error", async () => {
  const s = load({ sendMessage: async () => { throw new Error("Receiving end does not exist"); } });
  await s.ctx.dispatch({ platform: "mastodon", draft_id: "d10", content: "hi" });
  assert.equal(posted(s)[0].error, "Receiving end does not exist");
});

test("report: sends jwt and swallows network errors", async () => {
  const s = load({ storage: { jwt: "tok" }, routes: { "POST /posted": () => { throw new Error("offline"); } } });
  await s.ctx.report("d", { postUrl: "u" }); // must not throw
  assert.equal(s.fetchCalls[0].headers.Authorization, "Bearer tok");
});

// --- poll --------------------------------------------------------------------

test("poll: disabled extension does not hit the backend", async () => {
  const s = load({ storage: { enabled: false } });
  await s.ctx.poll();
  assert.equal(s.fetchCalls.length, 0);
});

test("poll: dispatches every queued item", async () => {
  const s = load({
    routes: {
      "GET /queue": {
        body: [
          { platform: "email", draft_id: "a", content: "SUBJECT: s\n\nb" },
          { platform: "nope", draft_id: "b", content: "x" },
        ],
      },
    },
  });
  await s.ctx.poll();
  assert.deepEqual(posted(s).map((p) => p.draft_id), ["a", "b"]);
});

test("poll: non-OK and network failures are swallowed", async () => {
  const s = load({ routes: { "GET /queue": { status: 500 } } });
  await s.ctx.poll();
  assert.equal(posted(s).length, 0);
  const s2 = load({ routes: { "GET /queue": () => { throw new Error("down"); } } });
  await s2.ctx.poll(); // must not throw
});

// --- outcomes ----------------------------------------------------------------

test("pollOutcomes: off by default", async () => {
  const s = load();
  const out = await s.ctx.pollOutcomes();
  assert.deepEqual({ ...out }, { ran: false, reason: "outcomes-disabled" });
  assert.equal(s.fetchCalls.length, 0);
});

test("pollOutcomes: HTTP and network failures surface a reason", async () => {
  const s = load({ storage: { outcomesEnabled: true }, routes: { "GET /drafts?status=posted": { status: 401 } } });
  assert.equal((await s.ctx.pollOutcomes()).reason, "HTTP 401");
  const s2 = load({
    storage: { outcomesEnabled: true },
    routes: { "GET /drafts?status=posted": () => { throw new Error("down"); } },
  });
  assert.equal((await s2.ctx.pollOutcomes()).reason, "fetch-failed: down");
});

test("pollOutcomes: scrapes eligible drafts, reports valid metrics, closes tabs, caps batch", async () => {
  const drafts = [{ id: "nourl" }];
  for (let i = 0; i < 10; i++) drafts.push({ id: `p${i}`, post_url: `https://x.com/s/${i}` });
  let call = 0;
  const s = load({
    storage: { outcomesEnabled: true, jwt: "j" },
    routes: { "GET /drafts?status=posted": { body: drafts } },
    executeScript: async (opts) => {
      if (opts.files) return [];
      call++;
      return [{ result: { source: "aria", metrics: { likes: 5, views: -1, comments: "x" } } }];
    },
  });
  const out = await s.ctx.pollOutcomes();
  assert.equal(out.ran, true);
  assert.equal(out.total_posted, 10);
  assert.equal(out.processed.length, 8); // OUTCOMES_MAX_PER_CYCLE
  assert.deepEqual({ ...out.processed[0].reported }, { likes: 5 });
  assert.equal(call, 8);
  assert.equal(s.tabsRemoved.length, 8);
  const outcomePosts = s.fetchCalls.filter((c) => c.method === "POST");
  assert.equal(outcomePosts.length, 8);
  assert.equal(outcomePosts[0].path, "/drafts/p0/outcomes");
  assert.deepEqual(outcomePosts[0].body, { metric_kind: "likes", metric_value: 5 });
  assert.equal(outcomePosts[0].headers.Authorization, "Bearer j");
});

test("pullOutcomesForDraft: extraction failure still closes the tab", async () => {
  const s = load({ executeScript: async () => { throw new Error("blocked"); } });
  const out = await s.ctx.pullOutcomesForDraft("http://api", "", { id: "d", post_url: "https://x.com/1" });
  assert.equal(out.source, "none");
  assert.deepEqual({ ...out.reported }, {});
  assert.deepEqual(s.tabsRemoved, [s.tabsCreated[0].id]);
  const skipped = await s.ctx.pullOutcomesForDraft("http://api", "", { id: "e" });
  assert.equal(skipped.skipped, "no post_url");
});

// --- wiring ------------------------------------------------------------------

test("scheduleAlarms creates poll + outcome alarms with configured interval", async () => {
  const s = load({ storage: { outcomesIntervalMinutes: 30 } });
  await s.ctx.scheduleAlarms();
  assert.deepEqual(s.alarmsCreated.map((a) => ({ ...a })), [
    { name: "fanout-poll", periodInMinutes: 0.5 },
    { name: "fanout-outcomes", delayInMinutes: 30, periodInMinutes: 30 },
  ]);
});

test("onMessage: poll-now / outcomes-now / reschedule respond and keep channel open", async () => {
  const s = load();
  const [listener] = s.chrome.runtime.onMessage.listeners;
  const respond = (type) =>
    new Promise((res) => {
      const keepOpen = listener({ type }, {}, res);
      assert.equal(keepOpen, true);
    });
  assert.deepEqual({ ...(await respond("fanout:poll-now")) }, { ok: true });
  const outcomes = await respond("fanout:outcomes-now");
  assert.equal(outcomes.ok, true);
  assert.equal(outcomes.reason, "outcomes-disabled");
  assert.deepEqual({ ...(await respond("fanout:reschedule-outcomes")) }, { ok: true });
  assert.equal(listener({ type: "other" }, {}, () => {}), undefined);
});

test("onInstalled / onStartup schedule alarms; onAlarm routes to poll", async () => {
  const s = load({ routes: { "GET /queue": { body: [] } } });
  s.chrome.runtime.onInstalled.listeners[0]();
  s.chrome.runtime.onStartup.listeners[0]();
  await new Promise((r) => setImmediate(r));
  assert.equal(s.alarmsCreated.length, 4);
  s.chrome.alarms.onAlarm.listeners[0]({ name: "fanout-poll" });
  await new Promise((r) => setImmediate(r));
  assert.ok(s.fetchCalls.some((c) => c.path === "/queue"));
});
