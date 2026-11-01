# Contributing to Fanout

Thanks for helping out! Fanout is three pieces — a Python backend, a Next.js web app, and a Chrome extension. You'll usually only touch one at a time.

## Local dev

```bash
scripts/dev.sh     # Postgres (docker compose) + backend :8000 + web :3000, bootstraps deps/env files
```

Then load the extension: `chrome://extensions` → Developer mode → Load unpacked → pick `./extension`.
See the README's "Run locally" section for the manual steps, and [`CLAUDE.md`](CLAUDE.md) for an
architecture/gotchas cheat sheet.

## Project layout

| Dir | What lives here |
|---|---|
| `backend/app/agent.py`   | Agentic pipeline (plan → write → critique → refine) + N-variations mode |
| `backend/app/main.py`    | FastAPI routes |
| `backend/app/store.py`   | Postgres CRUD scoped by `user_id` |
| `backend/app/models.py`  | SQLAlchemy models |
| `backend/app/research.py` | HN / Dev.to / Reddit / RSS signal fetchers + scoring |
| `backend/app/operator.py` | Autonomous experiment picker + `OperatorRun` audit trail |
| `backend/app/auth.py`    | Supabase JWT verification (dev-mode fallback when no secret) |
| `extension/src/background.js`   | Service worker: polls `/queue`, dispatches to the right content script |
| `extension/src/content-*.js`    | One per platform; drives that platform's composer |
| `web/app/page.tsx`       | Composer + draft picker + sticky action bar |
| `web/components/`        | Logo, Marquee, Spotlight, Typewriter, … |
| `web/lib/platforms.ts`   | Single source of truth for every supported channel |

## Adding a new channel

1. **Backend** — add the platform id to `PLATFORMS` and a rule string to `PLATFORM_RULES` in `backend/app/agent.py`.
2. **Web** — add a row to `web/lib/platforms.ts` with its brand icon, accent color, capability, and group.
3. **Extension** — add a routing entry to `PLATFORM_TARGETS` in `extension/src/background.js`. If it's auto-post, add a content script under `extension/src/content-<platform>.js` and register it in `manifest.json` (`content_scripts` + `host_permissions`).
4. **Test** — `curl` the `/variations` endpoint for the new platform and confirm output shape.

## Branches & commits

- Branch from `main`: `feature/<short-name>` or `fix/<short-name>`.
- Commit messages / PR titles use [Conventional Commits](https://www.conventionalcommits.org/) — `feat(backend): add bluesky content rules`, `fix(web): platform card hover`. release-please reads them to bump the version (root, `web/package.json`, `extension/manifest.json`) and write `CHANGELOG.md`, so don't bump versions by hand.
- Rebase on `main` before opening a PR.

## Pull requests

- One focused change per PR.
- Include a short "what / why / test plan" in the description.
- CI must be green: repo-layout check, backend compile + import smoke test + pytest (3.11 & 3.12),
  web `tsc --noEmit` + `next build`, extension manifest/syntax checks + outcome-extractor test.
  Run the same locally:

  ```bash
  python3 scripts/check_repo_layout.py
  cd backend && .venv/bin/python -m pytest tests/ -q
  cd web && npx tsc --noEmit && npx next build
  cd extension && for f in src/*.js; do node --check "$f"; done && node tests/test_outcomes.mjs
  ```

## Code style

- **Python:** type hints, no `# type: ignore` without a comment explaining why.
- **TypeScript:** strict mode is on; fix the root cause instead of casting.
- **Extension:** selectors rot. If you're adding DOM queries, list multiple fallbacks and comment *why* each exists.

## Testing tips

- Backend tests use in-memory SQLite and a dummy `GROQ_API_KEY` (see `backend/tests/conftest.py`) — no Postgres or network needed. LLM calls are faked by monkeypatching `SocialAgent._chat` / `.run` / `.variations`; HTTP-facing tests use FastAPI `TestClient`.
- To exercise generation for real, set `GROQ_API_KEY` in `backend/.env` and `curl` `/variations` (see `docs/RESEARCH_LOOP.md`). Always send `-H 'content-type: application/json'` — FastAPI rejects form-encoded bodies with 422.
- Extension debugging: `chrome://extensions` → Fanout → "Inspect views: service worker" for background logs, or open any target platform tab and open DevTools for content script logs.
- Backend: `uvicorn --reload` picks up changes automatically.

## Security

- **Never commit `.env` files.** Only `.env.example` / `.env.local.example` are tracked.
- The extension never stores passwords — users bring their own logged-in browser sessions.
- If you find a security issue, email the maintainer rather than opening a public issue.
