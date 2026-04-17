# Contributing to Fanout

Thanks for helping out! Fanout is three pieces — a Python backend, a Next.js web app, and a Chrome extension. You'll usually only touch one at a time.

## Local dev

See the README for the full bootstrap. Quick reminder:

```bash
# backend
cd backend && .venv/bin/uvicorn app.main:app --reload

# web
cd web && npm run dev

# extension
# chrome://extensions → Load unpacked → pick ./extension
```

## Project layout

| Dir | What lives here |
|---|---|
| `backend/app/agent.py`   | Agentic pipeline (plan → write → critique → refine) + N-variations mode |
| `backend/app/main.py`    | FastAPI routes |
| `backend/app/store.py`   | Postgres CRUD scoped by `user_id` |
| `backend/app/models.py`  | SQLAlchemy models |
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
- Commit messages: concise, imperative, scoped — `backend: add bluesky content rules`, `web: fix platform card hover`.
- Rebase on `main` before opening a PR.

## Pull requests

- One focused change per PR.
- Include a short "what / why / test plan" in the description.
- CI must be green (typecheck + build).

## Code style

- **Python:** type hints, no `# type: ignore` without a comment explaining why.
- **TypeScript:** strict mode is on; fix the root cause instead of casting.
- **Extension:** selectors rot. If you're adding DOM queries, list multiple fallbacks and comment *why* each exists.

## Testing tips

- Generate tests against Groq live (`.venv/bin/python /tmp/test_platforms.py` — see `docs/`).
- Extension debugging: `chrome://extensions` → Fanout → "Inspect views: service worker" for background logs, or open any target platform tab and open DevTools for content script logs.
- Backend: `uvicorn --reload` picks up changes automatically.

## Security

- **Never commit `.env` files.** Only `.env.example` / `.env.local.example` are tracked.
- The extension never stores passwords — users bring their own logged-in browser sessions.
- If you find a security issue, email the maintainer rather than opening a public issue.
