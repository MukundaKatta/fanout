# Fanout

[![CI](https://github.com/MukundaKatta/fanout/actions/workflows/ci.yml/badge.svg)](https://github.com/MukundaKatta/fanout/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FMukundaKatta%2Ffanout&project-name=fanout&root-directory=web&env=NEXT_PUBLIC_API_URL%2CNEXT_PUBLIC_SUPABASE_URL%2CNEXT_PUBLIC_SUPABASE_ANON_KEY)

Agentic content studio for indie shippers. One product description → 5 distinct, platform-tailored drafts → posted from your own browser.

**15 channels:** LinkedIn · X · Threads · Bluesky · Mastodon · Instagram · Reddit · Hacker News · Product Hunt · Medium · Dev.to · Email · Telegram · Discord · Slack

## Architecture

```
web (Next.js 15)  ──►  backend (FastAPI + Postgres)  ──►  Groq (free Llama 3.3 70B)
                                  ▲
                                  │ polls every 30s
                                  │
                       extension (Chrome MV3) ── posts via your logged-in tabs
```

- **No third-party API keys** to authorise — extension drives composers in your own browser session
- **Auto-post** on LinkedIn, X, Threads, Bluesky, Mastodon
- **Assist / copy-and-open** for Reddit, HN, Product Hunt, Medium, Dev.to, Telegram, Discord, Slack
- **mailto:** for Email — opens your default mail client with subject + body filled
- **Research loop** pulls live signals from Hacker News, Dev.to, Reddit, and any RSS feed you point it at, so drafts can reference what's actually being discussed today
- Atomic claim via `SELECT ... FOR UPDATE SKIP LOCKED` so concurrent polls can't double-post

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
  app/store.py     SQLAlchemy-backed CRUD scoped by user_id
  app/main.py      REST endpoints
  tests/           pytest, mocked HTTP for research, sqlite-backed for store
extension/    Chrome MV3 extension that posts via your browser session
  src/background.js     polls /queue, dispatches to content scripts
  src/content-*.js      one per platform
web/          Next.js 15 + Tailwind + Supabase
  app/page.tsx          composer + draft picker + sticky action bar
  components/           Logo, Marquee, Spotlight, Typewriter, ...
```

## Research loop

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

## Security

See [SECURITY.md](SECURITY.md). Short version: the backend never holds your social
credentials — the extension drives composers in your own logged-in browser session.

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). `main` is protected; CI must
pass and changes flow through PRs.

## License

[MIT](LICENSE) © Mukunda Katta
