# Fanout

[![CI](https://github.com/MukundaKatta/fanout/actions/workflows/ci.yml/badge.svg)](https://github.com/MukundaKatta/fanout/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FMukundaKatta%2Ffanout&project-name=fanout&root-directory=web&env=NEXT_PUBLIC_API_URL%2CNEXT_PUBLIC_SUPABASE_URL%2CNEXT_PUBLIC_SUPABASE_ANON_KEY)

Agentic content studio for indie shippers. One product description → 5 distinct, platform-tailored drafts → posted from your own browser.

**15 channels:** LinkedIn · X · Threads · Bluesky · Mastodon · Instagram · Reddit · Hacker News · Product Hunt · Medium · Dev.to · Email · Telegram · Discord · Slack

## Architecture

```
                       ┌────────────────────────────────────────────┐
                       │           web (Next.js 15 + Tailwind)       │
                       │   /  composer  ·  /research  ·  /operator   │
                       └─────────────────┬──────────────────────────┘
                                         │ REST
                                         ▼
   ┌──────────────────────────────────────────────────────────────┐
   │            backend (FastAPI + Postgres + SQLAlchemy)          │
   │                                                                │
   │   /generate  /variations            ─►  Groq (free Llama 3.3)  │
   │   /research /research/sources/lead.   ─►  HN · Dev.to · Reddit │
   │   /operator/run /operator/tick/all          · RSS              │
   │   /drafts /drafts/{id}/outcomes                                │
   │   /queue /posted                                               │
   └─────────────┬─────────────────────────────────────────────────┘
                 │ polls every 30s          ▲
                 ▼                          │ POSTs engagement
   ┌─────────────────────────────────────────────────────────────┐
   │            extension (Chrome MV3) ── your browser session    │
   │  · posts drafts via X / LinkedIn / Threads / Bluesky / ...  │
   │  · outcome puller scrapes engagement off posted URLs        │
   └─────────────────────────────────────────────────────────────┘
```

- **No third-party API keys** to authorise — extension drives composers in your own browser session
- **Auto-post** on LinkedIn, X, Threads, Bluesky, Mastodon
- **Assist / copy-and-open** for Reddit, HN, Product Hunt, Medium, Dev.to, Telegram, Discord, Slack
- **mailto:** for Email — opens your default mail client with subject + body filled
- **Self-tuning research loop** — pulls live HN / Dev.to / Reddit / RSS signals, drafts cite which signals they used, posted drafts feed engagement back, and the operator biases the next cycle toward sources that produce hits
- Atomic claim via `SELECT ... FOR UPDATE SKIP LOCKED` so concurrent polls can't double-post

## The autonomy loop

Fanout's compounding piece — once configured, the whole loop runs on a cron
with no human in the middle:

```
research-tick   (:17 hourly) ─►  bank fresh signals from HN / Dev.to / Reddit / RSS
operator-tick   (:37 hourly) ─►  pick experiment + draft for each subscription
extension queue (every 30s)  ─►  post via your browser session
outcome puller  (every 60m)  ─►  scrape likes/comments/reposts/views from post URLs
                                 └─► leaderboard fills
                                         └─► next operator-tick weights
                                             toward sources that earned engagement
```

Each layer is independently usable — turn off the operator and use the
research workbench manually, or skip outcome polling and ground drafts
on live signals alone. They compose, they don't depend on each other.

| Stage | What runs | Where to wire it |
| --- | --- | --- |
| **Research** | `POST /research` (manual), `POST /research/tick/all` (cron) | `docs/RESEARCH_LOOP.md` |
| **Outcome feedback** | `POST /drafts/{id}/outcomes`, `GET /research/sources/leaderboard` | `docs/RESEARCH_LOOP.md#outcome-feedback-closing-the-loop` |
| **Operator** | `POST /operator/run` (manual), `POST /operator/tick/all` (cron) | `docs/OPERATOR.md` |
| **Extension outcome puller** | Background tabs on a configurable cadence | `extension/src/outcomes.js`, popup toggle |

## Run locally

Prereqs: Node 22+, Python 3.11+, Postgres, a free [Groq API key](https://console.groq.com/keys).

```bash
# 1. backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # paste your GROQ_API_KEY
createdb fanout
.venv/bin/uvicorn app.main:app --reload

# 2. web (in a second terminal)
cd web
npm install
cp .env.local.example .env.local   # for Supabase auth, otherwise leave blank
npm run dev
# open http://localhost:3000

# 3. extension (one-time)
# Chrome → chrome://extensions → Developer mode → Load unpacked → pick ./extension
```

## Auth (optional)

Runs in **dev mode** by default (single user, no login). To enable Supabase magic-link auth:

1. Create a free Supabase project
2. Set `SUPABASE_JWT_SECRET` in `backend/.env`
3. Set `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` in `web/.env.local`
4. Optionally point `DATABASE_URL` at the Supabase Postgres
5. After signing in, paste your access token into the extension popup so it can authenticate when polling

## Repo layout

```
backend/      FastAPI + agentic pipeline + Postgres store
  app/agent.py     plan → write → critique → refine + variations(N)
  app/research.py  HN / Dev.to / Reddit / RSS signal fetchers (no API keys)
  app/operator.py  autonomous experiment picker + OperatorRun audit trail
  app/store.py     SQLAlchemy-backed CRUD scoped by user_id
  app/main.py      REST endpoints
  migrations/      ordered .sql files (research, subscriptions, citations,
                     draft_outcomes, operator_runs, operator_subscriptions)
  tests/           pytest, mocked HTTP for research, sqlite-backed for store
extension/    Chrome MV3 extension that posts via your browser session
  src/background.js     polls /queue + outcome-puller alarm
  src/outcomes.js       engagement-metric extractor (aria-label + visible-text)
  src/content-*.js      one per platform
  tests/test_outcomes.mjs   pure-Node smoke test of the extractor
web/          Next.js 15 + Tailwind + Supabase
  app/page.tsx          composer + draft picker + sticky action bar
  app/research/         research workbench + research/operator subscriptions
  app/operator/         OperatorRun history timeline
  lib/api.ts            typed client for every endpoint above
  components/           Logo, Marquee, Spotlight, Typewriter, CitationsPill
docs/         deep-dive guides — start with RESEARCH_LOOP.md and OPERATOR.md
```

## Research loop

> Full reference: [`docs/RESEARCH_LOOP.md`](docs/RESEARCH_LOOP.md). This
> section is the 60-second tour.

Generation gets sharper when the agent has fresh signal to ground against.
Run a research pass before generating, then opt in with `use_research: true`:

```bash
# pull signals into your account (deduped per user_id)
curl -X POST http://localhost:8000/research \
  -H 'content-type: application/json' \
  -d '{"queries":["ai agents","content automation"],"rss_feeds":["https://news.ycombinator.com/rss"]}'

# generate drafts that reference the top unused snippets
curl -X POST http://localhost:8000/generate \
  -H 'content-type: application/json' \
  -d '{"product":"...","use_research":true}'
```

Snippets are scored by upstream popularity × recency (48h half-life), deduped
per `(user_id, url)`, and marked **used** the first time they feed into a
draft so the next research run pulls fresh material.

### Autonomous loop (recurring subscriptions)

Save a query/feed config once and let it refresh on its own:

```bash
# create a daily subscription
curl -X POST http://localhost:8000/research/subscriptions \
  -H 'content-type: application/json' \
  -d '{"name":"AI agents","queries":["ai agents","llm tooling"],"interval_hours":24}'

# tick the loop — runs every active subscription that's due
curl -X POST http://localhost:8000/research/tick
```

Two tick endpoints depending on use case:

- **`POST /research/tick`** — per-user, JWT auth. The "Run due now" button on
  the workbench hits this.
- **`POST /research/tick/all`** — service-auth (`X-Tick-Secret` header), fans
  out across every user in one request. **Disabled by default** — set
  `RESEARCH_TICK_SECRET` env var on the backend to enable.

For a real cron, use `/research/tick/all`. Wire it to **any** scheduler —
Vercel cron, Render scheduled job, or the bundled GitHub Action at
`.github/workflows/research-tick.yml`.

To enable the GitHub Action:

1. Set backend env var `RESEARCH_TICK_SECRET` to a strong random string
2. Set repo **Variable** `RESEARCH_TICK_ENABLED = "true"`
3. Set repo **Secret** `RESEARCH_TICK_URL` = `https://<your-backend>/research/tick/all`
4. Set repo **Secret** `RESEARCH_TICK_SECRET` to the same value as step 1

The action runs hourly. The tick endpoint is idempotent — subscriptions that
aren't due yet are skipped server-side, so over-polling is safe.

## Eva operator

> Full reference: [`docs/OPERATOR.md`](docs/OPERATOR.md).

The operator wraps `/generate` with two things the research loop alone can't
give you:

1. **An experiment picker** — biases snippet selection toward sources whose
   past drafts have produced engagement (via the leaderboard from outcomes).
   Cold-start safe: falls back to plain score-desc when no outcomes exist.
2. **An audit row** — every cycle logs product, platforms, picked snippet
   ids, draft ids, status and a human-readable notes string. Replayable
   from `/operator/runs` or the `/operator` page.

```bash
# one cycle, all platforms, leaderboard-weighted
curl -X POST http://localhost:8000/operator/run \
  -H 'content-type: application/json' \
  -d '{"product":"<blurb>","platforms":["x","linkedin"]}'

# save it as a recurring cycle on the workbench
curl -X POST http://localhost:8000/operator/subscriptions \
  -d '{"name":"daily-social","product":"<blurb>","platforms":["x","linkedin"]}'
```

Service-auth tick + bundled GitHub Action at
`.github/workflows/operator-tick.yml` mirror the research-tick setup —
enable with `OPERATOR_TICK_ENABLED=true` + `OPERATOR_TICK_URL` +
`OPERATOR_TICK_SECRET`. Runs at minute :37 hourly, deliberately offset from
research-tick at :17 so they don't fight for backend attention.

## Extension outcome puller

> Wired into the popup; off by default until you opt in.

The Chrome extension already posts drafts via your browser session. The
outcome puller closes the loop: it visits each posted-draft URL on a
configurable cadence (default 60 min), scrapes engagement via a
DOM-agnostic extractor, and POSTs the metrics to `/drafts/{id}/outcomes`
so the leaderboard fills.

- **Two-pass extractor:** aria-label scan first (X / Bluesky / Threads
  carry exact counts there), then visible-text fallback
  (LinkedIn / Mastodon). Max wins so an `aria-label="1,234 likes"`
  beats a visible `"1.2K likes"` rounded form.
- **Normalizes** `1,234` / `1.2K` / `1.5M` / `1B` to an int. Open metric
  vocabulary — recognizes likes / favorites, comments / replies, reposts
  / retweets / boosts / reblogs / shares, views / impressions, clicks,
  saves / bookmarks.
- **Defaults off:** opening background tabs to social pages requires
  explicit consent via the popup toggle.

## Deploying the web app

**Easy mode — Vercel native git integration (recommended):**

1. Click [![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FMukundaKatta%2Ffanout&project-name=fanout&root-directory=web&env=NEXT_PUBLIC_API_URL%2CNEXT_PUBLIC_SUPABASE_URL%2CNEXT_PUBLIC_SUPABASE_ANON_KEY) above
2. Set `Root Directory` to `web` when prompted
3. Provide the three `NEXT_PUBLIC_*` env vars
4. Vercel auto-deploys on every push to `main`

**Optional — CI-driven deploy from GitHub Actions:**

The repo includes [`.github/workflows/deploy-web.yml`](.github/workflows/deploy-web.yml). It runs only when you set:

- Secret `VERCEL_TOKEN`
- Secret `VERCEL_ORG_ID`
- Secret `VERCEL_PROJECT_ID`
- Variable `VERCEL_DEPLOY_ENABLED=true`

This lets CI gate the deploy and post the live URL back to the commit.

## Tests

Two backend test suites, by design:

```bash
# Full suite — needs the backend deps installed (FastAPI, SQLAlchemy, …).
# sqlite-backed store tests + mocked-HTTP research tests + operator/agent tests.
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/ -q

# Dependency-free smoke suite — pure standard library, runs from a clean
# checkout with nothing installed. Locks down the research loop's scoring,
# recency decay, ISO/RFC-822 parsing, dedup, and prompt formatting.
python3 -m unittest discover -s tests          # run from the repo root
```

The stdlib suite (`tests/`) imports only `app.research`, which is itself
standard-library-only, so it doubles as a guard that the research module never
silently grows a third-party dependency. The extension has its own pure-Node
smoke test:

```bash
node extension/tests/test_outcomes.mjs
```

All three run in CI (`.github/workflows/ci.yml`).

## Security

See [SECURITY.md](SECURITY.md). Short version: the backend never holds your social
credentials — the extension drives composers in your own logged-in browser session.

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). `main` is protected; CI must
pass and changes flow through PRs.

CI includes a repository-layout contract check for the backend, web app, and
Chrome extension so future refactors do not accidentally remove a deployable
surface.

## License

[MIT](LICENSE) © Mukunda Katta
