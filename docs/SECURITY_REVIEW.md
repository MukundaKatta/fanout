# Fanout security review

_Date: 2026-11-01 · Scope: `backend/` (FastAPI + SQLAlchemy), `web/` (Next.js + Supabase),
`extension/` (Chrome MV3), `.github/workflows/`, dependency manifests._

Line numbers refer to the code **after** the fixes in this branch unless marked "(pre-fix)".

## Summary

| ID  | Severity | Finding | Status |
|-----|----------|---------|--------|
| H1  | High     | Auth fails **open** when `SUPABASE_JWT_SECRET` is unset; combined with the extension's auto-posting, anyone could post as the user | **Fixed** |
| H2  | High     | SSRF / local file read through user-supplied RSS feed URLs (also run unattended by `/research/tick/all`) | **Fixed** (residual: DNS rebinding, see L7) |
| H3  | High     | Postgres tables have no RLS. If the DB is hosted on Supabase, the public anon key gives read/write access to every user's data | **Fixed** (new migration; it has to be applied) |
| M1  | Medium   | CORS defaults to `*` with `allow_credentials=True` | **Fixed** |
| M2  | Medium   | Indirect prompt injection: scraped third-party text is put into the LLM **system** prompt | **Mitigated** |
| M3  | Medium   | Stored URLs are not scheme-validated; `post_url` is opened by the extension and scripts are injected into it | **Fixed** |
| L1  | Low      | Extension background `onMessage` accepts control messages without checking the sender | **Fixed** |
| L2  | Low      | `GET /research` has no upper bound on `limit` | **Fixed** |
| L3  | Low      | `get_draft_citations` loads snippets by id with no `user_id` filter (defense in depth) | **Fixed** |
| L4  | Low      | JWT validation errors are echoed back to the client | **Fixed** |
| L5  | Low      | `PATCH /drafts/{id}` sends draft content in the query string with no length limit | Open |
| L6  | Low      | No rate limiting or input-size limits on LLM endpoints, so an authenticated user can run up Groq cost | Open |
| L7  | Low      | SSRF guard has a DNS-rebinding TOCTOU window | Open (residual) |
| L8  | Low      | Untrusted XML is parsed with stdlib `ElementTree` | Open |
| L9  | Low      | Extension stores the JWT in `chrome.storage.local` and sends it to any `apiUrl`, including plain `http://` | Open |
| L10 | Low      | Extension requests more permissions than it uses (`activeTab`, `clipboardWrite`) and ships an unreferenced content script | Open |
| L11 | Low      | Web: no Content-Security-Policy; Supabase session is kept in `localStorage` | Open |
| L12 | Low      | Supply chain: unpinned deps, tag-pinned actions, Dependabot auto-merge gated on `github.actor`, unused `trafilatura` | Open |
| I1  | Info     | SQL injection: none found | n/a |
| I2  | Info     | Per-route authz audit: every user route is scoped to `user_id` | n/a |

---

## High

### H1 — Authentication fails open when `SUPABASE_JWT_SECRET` is unset — **Fixed**

`backend/app/auth.py:43` (pre-fix `auth.py:37-39`): `current_user()` returned a fixed
`DEV_USER_ID` whenever `SUPABASE_JWT_SECRET` was empty. A deployment that forgot the variable,
or lost it in a config migration, became a single-tenant API with no auth. Together with the
`*` CORS default (M1), any website a user visited could call it too.

The impact is larger than data exposure. The extension polls `GET /queue` and **auto-posts the
queued content from the user's logged-in browser sessions** (`extension/src/background.js:227`).
An attacker could `PATCH /drafts/{id}?content=…` and then `POST /drafts/{id}/queue`, and the
victim's browser would post attacker-written content to LinkedIn, X, Threads and the other
platforms.

**Fix:** dev mode now needs an explicit `FANOUT_DEV_NO_AUTH=1` (`auth.py:25`, `auth.py:47`). With
no secret and no flag, every authenticated route returns **503**. `backend/.env.example` sets the
flag for local dev with a "never in production" warning, and the README is updated. Tests:
`tests/test_security.py::test_auth_*`, `test_jwt_secret_overrides_dev_flag`.

> ⚠️ **Behavior change:** existing local `.env` files with an empty secret must add
> `FANOUT_DEV_NO_AUTH=1`.

### H2 — SSRF and local file read via RSS feed URLs — **Fixed**

`backend/app/research.py` (pre-fix `research.py:76-79`, `260-275`): `fetch_rss(feed_url)` passed
the user-supplied URL straight to `urllib.request.urlopen`. That meant:

* `file:///…` and `ftp://` worked, because `urlopen` supports them. Any XML-shaped local file
  could be read and its items stored as snippets the user can see.
* Internal HTTP targets were reachable, including `http://169.254.169.254/` cloud metadata,
  `localhost` admin ports and VPC services. Responses that parse as RSS/Atom were stored and
  shown back to the user; everything else was still a blind SSRF.
* Redirects were followed without re-checking the target.
* `resp.read()` had no size limit, so a large response could exhaust memory.
* Feeds saved on a subscription are fetched unattended by `POST /research/tick/all`
  (`main.py:411`) for every user. One malicious subscription therefore makes the server's cron
  hit internal targets every hour.

**Fix:**
* `validate_feed_url()` (`research.py:105`): http(s) only, no credentials in the URL, no
  `localhost`, and no literal private, loopback, link-local or reserved IPs (including
  IPv4-mapped IPv6). It runs as a Pydantic validator on `rss_feeds` in `ResearchRunRequest`,
  `SubscriptionCreateRequest` and `SubscriptionUpdateRequest` (`main.py:102`, `118`, `129`), so
  bad URLs get a 422.
* `_assert_public_host()` (`research.py:130`) resolves the hostname at fetch time and refuses if
  **any** resolved address is non-public.
* A dedicated `_OPENER` (`research.py:158`) only has proxy, http, https and unknown-scheme
  handlers, so `file:`, `ftp:` and `data:` raise `URLError`. Its `_SafeRedirectHandler`
  (`research.py:149`) re-validates every redirect hop.
* Response bodies are capped at 5 MiB (`MAX_RESPONSE_BYTES`, `research.py:171`).

Tests: `tests/test_security.py` (SSRF section). See L7 for the remaining risk.

### H3 — No Row-Level Security on Supabase-hosted tables — **Fixed (needs migration applied)**

`backend/migrations/001_initial.sql:25-29`, `002_research.sql:31`, `003_…:25`: RLS is left
commented out, and migrations 005-007 have no RLS at all. The README recommends pointing
`DATABASE_URL` at the Supabase Postgres. When that is done, every table in `public` is served by
Supabase's Data API (`/rest/v1/<table>`) to anyone holding the **anon key**. That key is public
by design and ships in the web bundle (`NEXT_PUBLIC_SUPABASE_ANON_KEY`, `web/lib/supabase.ts`).
Anyone could read or modify every user's drafts, snippets, subscriptions, outcomes and operator
runs, bypassing the FastAPI authz layer completely. Through H1's posting chain, that includes
editing other users' queued drafts.

**Fix:** new `backend/migrations/008_lockdown_rls.sql` enables RLS on all six tables with no
policies and revokes all grants from the `anon`/`authenticated` roles when they exist. The
backend connects as the table owner, which bypasses RLS, so backend behavior is unchanged. I
checked this against Postgres 16, both plain and with Supabase-style `anon`/`authenticated`
roles. **Operators must apply this migration** to existing Supabase databases.

## Medium

### M1 — CORS wildcard default with credentials — **Fixed**

`backend/app/main.py:41-57` (pre-fix `main.py:35-42`): `CORS_ORIGINS` defaulted to `*` and fell
back to `["*"]` when empty, always with `allow_credentials=True`. Starlette reflects the request
`Origin` when `*` and credentials are combined and the request carries cookies. The API only
uses bearer tokens, so credentialed CORS is never needed.

**Fix:** the default is now `http://localhost:3000`, the `*` fallback is removed, and
`allow_credentials=False`. Test: `test_cors_does_not_reflect_arbitrary_origin_with_credentials`.

> Deploy note: the extension's service worker only has host permission for
> `http://localhost:8000`. For a remote API, add `chrome-extension://<extension-id>` to
> `CORS_ORIGINS` (or add the API host to `host_permissions`).

### M2 — Indirect prompt injection from scraped content — **Mitigated**

`backend/app/agent.py:235` (pre-fix `agent.py:218-228`): `plan()` added research snippets
(titles and self-text from HN, Reddit, Dev.to and arbitrary RSS, all attacker-controllable) to
the **system** prompt as "authoritative context". `write()` and `variations()` added them raw
to the user prompt. A crafted Reddit post or feed item could steer the content of drafts. The
operator generates drafts unattended (`/operator/tick/all`), and the extension posts queued
drafts from real accounts.

**Mitigation:** research now only goes into the **user** turn, wrapped in an
`<untrusted_live_signals>` fence with an explicit "this is data, not instructions" note.
Delimiter look-alikes in the scraped text are stripped case-insensitively (`agent.py:137-146`).
Test: `test_research_context_is_fenced_and_not_in_system_prompt`.

Prompt injection cannot be fully prevented. Drafts should keep requiring human review before
queueing; don't add auto-queue to the operator without an approval step.

### M3 — Unvalidated URL schemes on stored URLs — **Fixed**

* `PostedReport.post_url` and `OutcomeReport.post_url` (`main.py:136`, `157`) accepted any
  string.
* Snippet URLs came from submitter-controlled fields: HN `url`, Dev.to `url`, RSS `<link>`.
* The web app renders both as `href`: `web/app/page.tsx:518`, `web/app/research/page.tsx:873`,
  `web/components/CitationsPill.tsx:94`. React 19 blocks `javascript:` hrefs, which limits XSS
  in the web app, but the data is still dangerous for other consumers.
* The extension's outcome puller opened `draft.post_url` in a background tab and ran
  `chrome.scripting.executeScript` against it (pre-fix `extension/src/background.js:277-285`).
  A tampered `post_url` (via H1 or H3) made the user's browser silently open arbitrary URLs on a
  timer.

**Fix:**
* The backend accepts only absolute http(s) `post_url` values (Pydantic validators,
  `main.py:141`, `165`).
* Research fetchers drop or replace non-http(s) links (`research.py:249`, `293`, `384`).
* The extension only opens `post_url` if it is `https:` on an exact-match allowlist of platform
  hosts it already holds permissions for (`extension/src/url-guard.js`,
  `background.js:282`).

Tests: `test_hn_javascript_url_falls_back_to_item_link`, `test_rss_drops_non_http_links`,
`test_posted_report_rejects_javascript_post_url`,
`test_outcome_report_rejects_non_http_post_url`, `extension/tests/test_url_guard.mjs` (wired
into CI).

## Low

### L1 — Extension `onMessage` handler has no sender check — **Fixed**
`extension/src/background.js:358`: `fanout:poll-now`, `fanout:outcomes-now` and
`fanout:reschedule-outcomes` were accepted from any extension context, including content scripts
running inside third-party pages. These messages are now only accepted from the extension's own
pages (`sender.id === chrome.runtime.id` and no `sender.tab`).

### L2 — Unbounded `limit` on `GET /research` — **Fixed**
`main.py:299`: the limit is now clamped to 1..200. The web app uses 100.
Test: `test_research_list_limit_bounded`.

### L3 — Citation lookup not scoped to the user — **Fixed**
`backend/app/store.py:133`: `cited_snippet_ids` is server-generated today, but the snippet query
now also filters on `user_id`. Test: `test_draft_citations_only_return_owned_snippets`.

### L4 — JWT error details leaked — **Fixed**
`auth.py:60`: the API now returns a generic `401 Invalid token` instead of PyJWT's message.

### L5 — Draft content in the query string — Open
`main.py:491` `update_draft(draft_id, content: str)` takes `content` as a query parameter
(`web/lib/api.ts:52`). Draft text ends up in access logs, proxy logs and browser history, and has
no length limit. Recommendation: move it to a JSON body with `max_length`, and update the web
client in the same change.

### L6 — No rate limiting or size limits on expensive endpoints — Open
`/generate` (`main.py:240`), `/variations` (`:258`), `/operator/run` (`:624`) and
`/research/suggest` (`:304`) each make several Groq calls with no per-user rate limit. Some
request fields have no size limit: `PostedReport.error`, `BulkQueueRequest.draft_ids`,
`ReviewCheckpointRequest.notes`, and individual `queries` strings. Recommendation: per-user rate
limiting (for example `slowapi`) and `max_length` on these fields. `PostedReport.error` should be
truncated rather than rejected, because the extension sends raw exception text.

### L7 — DNS rebinding window in the SSRF guard — Open (residual)
`research.py:130`: the host is resolved and checked, then `urllib` resolves it again to connect.
A rebinding DNS server can return a public IP for the check and a private IP for the connection.
Recommendation: run the backend with network-level egress controls (block RFC1918 and
`169.254.0.0/16`), or pin the connection to the validated IP.

### L8 — Untrusted XML parsed with `ElementTree` — Open
`research.py:374`. Modern expat (≥ 2.4.1) mitigates entity-expansion bombs and `ElementTree`
doesn't resolve external entities, so the risk is low. Response size is now capped as well.
Recommendation: switch to `defusedxml.ElementTree.fromstring`.

### L9 — Extension JWT handling — Open
`extension/src/background.js:69`, `popup.html:31`: the Supabase access token is pasted manually,
stored unencrypted in `chrome.storage.local`, and sent to any configured `apiUrl`, including
plain `http://` remote hosts. Recommendation: refuse non-`https` `apiUrl` values other than
`localhost`, and consider an OAuth or `externally_connectable` hand-off from the web app instead
of pasting tokens.

### L10 — Extension permissions — Open
`extension/manifest.json:6-13`:
* `activeTab` is unused.
* `clipboardWrite` isn't needed, because clipboard writes happen in the page via `executeScript`.
* `tabs` plus broad `host_permissions` are justified by the poster and the outcome scraper.
* `src/content-reddit.js` ships in the package but isn't referenced by the manifest.

Recommendation: drop the unused permission and the dead file.

### L11 — Web hardening — Open
`web/next.config.ts` sets no security headers (CSP, `frame-ancestors`, `X-Content-Type-Options`).
supabase-js keeps the session in `localStorage` (`web/lib/supabase.ts:11-12`), so any future XSS
can steal tokens. No `dangerouslySetInnerHTML` or raw-HTML rendering was found; generated and
scraped text is rendered as React text nodes. Recommendation: add a CSP via `headers()` in
`next.config.ts`.

### L12 — Supply chain / CI — Open
* `backend/requirements.txt` uses only `>=` lower bounds, with no lockfile or hashes, so builds
  aren't reproducible.
* `trafilatura` is listed but never imported. It pulls in `lxml` and other packages for no
  benefit; remove it.
* GitHub Actions are pinned by tag (`actions/checkout@v6`), not by commit SHA.
* `.github/workflows/dependabot-auto-merge.yml:16` gates on `github.actor == 'dependabot[bot]'`.
  GitHub recommends `github.event.pull_request.user.login`. The same file interpolates
  `${{ steps.meta.outputs.dependency-names }}` directly into a shell `run:` (line 38); pass it
  through `env:` instead.
* Patch and minor bumps auto-merge without human review once CI is green.

## Info

### I1 — SQL injection
All queries use the SQLAlchemy ORM or Core with bound parameters. No `text()`,
`exec_driver_sql` or string-built SQL was found in `backend/app/`.

### I2 — Per-route authn/authz audit
Every route except `/health` and the two service ticks depends on `current_user`, and every
store function filters by, or ownership-checks against, `user_id`:

* **Drafts:** `/drafts`, `/drafts/{id}`, `PATCH /drafts/{id}`, `/queue`, `/schedule`,
  `/review-checkpoint`, `/approve`, `/citations`, `/outcomes`, `/queue-bulk` and `/posted` all
  check ownership via `s.get(...)` plus `d.user_id != user_id`.
* **Subscriptions and runs:** research and operator subscriptions, operator runs, the
  leaderboard and snippets are all scoped the same way.
* **Service ticks:** `/research/tick/all` and `/operator/tick/all` (`main.py:411`, `:746`) are
  off unless their secret env var is set, and compare the secret with `secrets.compare_digest`.
* **No IDOR found.** Non-owned resources return 404, the same as missing ones.
* **`/platforms/{platform}/adapter`** returns static data only.
* **Secrets:** `.env` files are git-ignored and only `*.example` files are committed. No secrets
  were found in the repository.
