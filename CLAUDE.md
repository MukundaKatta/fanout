# CLAUDE.md

Guidance for AI assistants (and humans) working in this repo. Keep it accurate —
if you change something described here, update this file in the same PR.

## What this is

Fanout turns one product description into platform-tailored social drafts and
posts them from the user's own browser. Three deployable surfaces plus a cron loop:

| Dir | Stack | Role |
| --- | --- | --- |
| `backend/` | FastAPI, SQLAlchemy 2, Postgres (psycopg 3), Groq SDK | REST API, LLM pipeline, research fetchers, operator, all persistence |
| `web/` | Next.js 16 (App Router, Turbopack), React 19, Tailwind 4, Supabase JS | Composer UI (`/`), research workbench (`/research`), operator history (`/operator`) |
| `extension/` | Chrome MV3, plain ES modules, no build step | Polls `/queue`, drives each platform's composer, scrapes engagement back |
| `scripts/` | bash / python | `dev.sh` (local stack), `check_repo_layout.py` (CI contract) |
| `docs/` | markdown | `RESEARCH_LOOP.md`, `OPERATOR.md` deep dives |

Flow: web → `POST /generate` → `SocialAgent` (plan → write → critique → refine via
Groq) → `drafts` rows (`pending`) → user queues/schedules → extension polls
`GET /queue` every 30 s, posts, reports `POST /posted` → optional outcome puller
POSTs `/drafts/{id}/outcomes` → `/research/sources/leaderboard` → operator weights
the next cycle toward sources that earned engagement.

## Running things

```bash
scripts/dev.sh            # Postgres (docker compose) + backend :8000 + web :3000; bootstraps venv/npm/env files
scripts/dev.sh --setup    # bootstrap only;  --no-db  to skip Docker and use DATABASE_URL as-is
docker compose up -d db   # just Postgres (postgres/postgres@localhost:5432/fanout)
```

Manual equivalents and the extension load steps are in README "Run locally".

### Checks (mirror `.github/workflows/ci.yml`)

```bash
python3 scripts/check_repo_layout.py

cd backend
.venv/bin/python -m pytest tests/ -q                 # ~2 s, sqlite in-memory, no network/Postgres/Groq
.venv/bin/python -m pytest tests/test_operator.py -q # single file
.venv/bin/python -m compileall -q app

cd web
npx tsc --noEmit
npx next build      # NEXT_TELEMETRY_DISABLED=1 in CI

cd extension
for f in src/*.js; do node --check "$f"; done
node tests/test_outcomes.mjs                          # pure-Node, no test framework
```

There is no linter/formatter configured in CI (no ruff/eslint/prettier); match the
surrounding style. `.editorconfig` sets basics.

## Backend map (`backend/app/`)

- `main.py` — every route, plus the Pydantic request models. Loads `backend/.env`
  at import (path-relative, works from any cwd). `lifespan` calls `init_db()`.
- `db.py` — engine built **at import time** from `DATABASE_URL`
  (default `postgresql+psycopg://postgres:postgres@localhost:5432/fanout`).
  `init_db()` = `Base.metadata.create_all`. `session_scope()` commits/rolls back.
- `models.py` — `Draft`, `ResearchSnippet`, `ResearchSubscription`, `DraftOutcome`,
  `OperatorRun`, `OperatorSubscription`. String UUID PKs, tz-aware UTC timestamps,
  generic `JSON` columns (so the same models work on sqlite in tests).
- `store.py` — all DB access. Functions take `user_id` first and return plain
  dicts (never ORM objects). Every user-facing query is scoped by `user_id`.
- `agent.py` — `SocialAgent`, `PLATFORMS` (15 ids), `PLATFORM_RULES`. Single LLM
  choke point is `SocialAgent._chat`. `Groq()` is constructed in `__init__`, so
  `GROQ_API_KEY` is only needed when an LLM endpoint is actually hit.
- `research.py` — HN / Dev.to / Reddit / RSS fetchers over stdlib `urllib`
  (no API keys), scoring = `sqrt(popularity × recency)`, 48 h half-life.
- `operator.py` — `run()` one cycle (pick snippets, weighted by leaderboard →
  generate → audit row), `tick_user`, `tick_all`.
- `auth.py` — `current_user` dependency. **No `SUPABASE_JWT_SECRET` ⇒ dev mode**:
  every request is user `00000000-0000-0000-0000-000000000000`.

Draft status lifecycle: `pending` → (`review_required` →) `queued` | `scheduled`
→ `posting` (claimed by `GET /queue`) → `posted` | `failed`.

## Conventions

- **Adding a platform** touches four places that must stay in sync:
  `PLATFORMS` + `PLATFORM_RULES` in `backend/app/agent.py`, `web/lib/platforms.ts`,
  `PLATFORM_TARGETS` in `extension/src/background.js` (+ content script and
  `manifest.json` `content_scripts`/`host_permissions` for auto-post). CI asserts
  `len(PLATFORMS) == 15` — bump that in `ci.yml` too. See CONTRIBUTING.
- **Schema changes**: edit `models.py` *and* add the next numbered
  `backend/migrations/00N_*.sql` (idempotent `IF NOT EXISTS` style). `create_all`
  only creates missing tables — it never adds columns to existing ones, so a local
  DB that predates your change needs the migration applied or
  `docker compose down -v` to reset.
- New store functions: take `user_id`, open `session_scope()`, return dicts.
  Add tests next to the existing `tests/test_store_*.py`.
- Tests fake the LLM by monkeypatching `SocialAgent._chat` / `.run` / `.variations`
  and HTTP fetchers in `research`; endpoint tests use FastAPI `TestClient`.
  Never hit the network in tests.
- Web: all backend calls go through `web/lib/api.ts` (typed; attaches the Supabase
  bearer token when auth is enabled). TS strict — no casting around errors.
  Path alias `@/*` → `web/*`. Pages are client components (`"use client"`).
- Extension: no bundler; DOM selectors rot, so list fallbacks and comment why.
- Commits / PR titles: Conventional Commits (`feat(web): …`, `fix(backend): …`).
  release-please derives versions + `CHANGELOG.md` from them and bumps
  `web/package.json` + `extension/manifest.json` — never bump versions by hand.
- Never commit `.env` / `.env.local`; only the `*.example` files are tracked and
  they must list every env var the code reads.

## Env vars

Backend (`backend/.env`, see `.env.example`): `GROQ_API_KEY`, `GROQ_MODEL`,
`DATABASE_URL`, `SUPABASE_JWT_SECRET`, `SUPABASE_JWT_AUDIENCE`, `CORS_ORIGINS`,
`RESEARCH_TICK_SECRET`, `OPERATOR_TICK_SECRET`.
Web (`web/.env.local`, see `.env.local.example`): `NEXT_PUBLIC_API_URL`,
`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
Extension: none — API URL, JWT and toggles live in `chrome.storage.local` via the popup.

## Gotchas

- **`DATABASE_URL` is read at import time** (`app/db.py`). Tests set it in
  `tests/conftest.py` *before* importing `app`; do the same in any script.
  Real env vars beat `backend/.env` (`load_dotenv` doesn't override).
- Tests run on sqlite, so Postgres-only behaviour (e.g. `FOR UPDATE SKIP LOCKED`
  in `store.due_for_posting`, which sqlite ignores) isn't covered — check those against
  `docker compose up -d db` manually.
- **`GET /queue` is not a read** — it atomically claims due drafts and flips them
  to `posting`. Don't curl it to "look"; use `GET /drafts?status=queued`.
- **Setting the Supabase vars in `web/.env.local` enables the login gate.**
  Placeholder values (e.g. `https://your-project.supabase.co`) break the app;
  leave them empty for dev mode. If enabled on web, the backend needs
  `SUPABASE_JWT_SECRET` or tokens won't verify (and vice versa: backend secret
  without web auth ⇒ every call 401s).
- `curl` examples must send `-H 'content-type: application/json'`; without it
  FastAPI returns 422.
- `/research/tick/all` and `/operator/tick/all` return 403 until
  `RESEARCH_TICK_SECRET` / `OPERATOR_TICK_SECRET` are set (by design).
- The extension's `host_permissions` only include `http://localhost:8000/*`. A
  backend on another port/host needs an entry in `extension/manifest.json`.
- `NEXT_PUBLIC_*` values are inlined at build time — restart `next dev` /
  rebuild after changing them.
- `next dev` rewrites `web/tsconfig.json` and `web/next-env.d.ts` (Next 16
  type-gen paths). Don't commit those diffs unless you meant to upgrade config.
  It also (re)creates `web/AGENTS.md` / `web/CLAUDE.md` when it detects an AI
  agent; those are committed so the tree stays clean — read them before
  writing Next.js code (they point at version-matched docs in `node_modules`).
- Web dependency versions in `package.json` are newer than some docs/blog posts
  assume (Next 16, React 19, Tailwind 4 via `@tailwindcss/postcss`).
- Groq free tier rate-limits; `/generate` for all 15 platforms is many calls
  (plan + write/critique/refine per platform) and can take a while.
