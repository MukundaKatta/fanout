// Smoke tests for the outcome-metric extractor. Stubs a minimal DOM so
// outcomes.js can run under plain `node` (no jsdom dep). Add fixtures
// here whenever you wire a new platform.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(resolve(here, "../src/outcomes.js"), "utf8");

function runFixture(ariaLabels, text) {
  const ariaNodes = ariaLabels.map((label) => ({ getAttribute: () => label }));
  globalThis.window = {};
  globalThis.document = {
    querySelectorAll: (sel) => (sel.includes("aria-label") ? ariaNodes : []),
    body: { innerText: text },
  };
  // Re-eval each time so the IIFE freshly rebinds window.__fanoutExtractMetrics.
  // eslint-disable-next-line no-eval
  eval(src);
  return globalThis.window.__fanoutExtractMetrics();
}

let failures = 0;
function assert(cond, label, ctx) {
  if (!cond) {
    failures++;
    console.error("FAIL:", label, ctx);
  }
}

// --- X (Twitter) — aria-labels carry the precise counts ----------------------
const x = runFixture(
  ["1,234 likes", "56 replies", "1.2K reposts", "12,345 views"],
  ""
);
assert(x.metrics.likes === 1234, "x likes", x);
assert(x.metrics.comments === 56, "x comments", x);
assert(x.metrics.reposts === 1200, "x reposts", x);
assert(x.metrics.views === 12345, "x views", x);
assert(x.source === "aria", "x source", x.source);

// --- LinkedIn — visible-text scan -------------------------------------------
const li = runFixture(
  [],
  "Joe Lee and 47 others 12 comments 3 reposts"
);
assert(li.metrics.comments === 12, "li comments", li);
assert(li.metrics.reposts === 3, "li reposts", li);

// --- Bluesky — "23 likes 7 reposts 4 replies" -------------------------------
const bsky = runFixture([], "23 likes 7 reposts 4 replies");
assert(bsky.metrics.likes === 23, "bsky likes", bsky);
assert(bsky.metrics.reposts === 7, "bsky reposts", bsky);
assert(bsky.metrics.comments === 4, "bsky comments", bsky);

// --- Mastodon — "favorites" + "boosts" aliases ------------------------------
const mast = runFixture([], "5 favorites 2 boosts 1 reply");
assert(mast.metrics.likes === 5, "mast favorites→likes", mast);
assert(mast.metrics.reposts === 2, "mast boosts→reposts", mast);
assert(mast.metrics.comments === 1, "mast reply→comments", mast);

// --- K/M suffix normalization -----------------------------------------------
const kn = runFixture(["1.5K likes"], "");
assert(kn.metrics.likes === 1500, "kn 1.5K", kn);

// --- Empty page → empty metrics --------------------------------------------
const empty = runFixture(["Profile"], "Welcome back");
assert(
  Object.keys(empty.metrics).length === 0,
  "empty page returns no metrics",
  empty
);

// --- Max-wins: aria=1234, text=1.2K → keep 1234 -----------------------------
const both = runFixture(["1,234 likes"], "1.2K likes");
assert(both.metrics.likes === 1234, "both: max wins", both);

// --- Bogus word: number adjacent to a non-metric word → no metric -----------
const bogus = runFixture([], "42 frobozz");
assert(
  Object.keys(bogus.metrics).length === 0,
  "bogus word does not register",
  bogus
);

if (failures > 0) {
  console.error(`\n${failures} test(s) failed`);
  process.exit(1);
}
console.log("OK — all outcome-extraction fixtures pass");
