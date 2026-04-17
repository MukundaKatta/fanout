# Fanout

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
  app/store.py     SQLAlchemy-backed CRUD scoped by user_id
  app/main.py      REST endpoints
extension/    Chrome MV3 extension that posts via your browser session
  src/background.js     polls /queue, dispatches to content scripts
  src/content-*.js      one per platform
web/          Next.js 15 + Tailwind + Supabase
  app/page.tsx          composer + draft picker + sticky action bar
  components/           Logo, Marquee, Spotlight, Typewriter, ...
```

## License

MIT
