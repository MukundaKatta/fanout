# Research loop — operator's guide

Fanout's research loop pulls live signals (HN, Dev.to, Reddit, RSS) and folds them into the agent's prompt so drafts can reference what's actually being discussed today, not just the static product blurb.

This doc walks the loop end-to-end — what the pieces are, how to wire them, and how to verify each step is doing what you expect.

## At a glance

```
   ┌────────────────────┐
   │ /research/suggest  │ ← seed queries from a product blurb (cuts cold-start)
   └──────────┬─────────┘
              │
   ┌──────────▼─────────┐    ┌──────────────────────┐
   │ /research          │ ←─ │ subscriptions + cron │
   │ (manual / per-tick)│    │ /research/tick[/all] │
   └──────────┬─────────┘    └──────────────────────┘
              │ persists, deduped per (user_id, url)
              ▼
   ┌────────────────────┐
   │  research_snippets │ ← scored by popularity × recency
   └──────────┬─────────┘
              │ top N unused fed into prompt when use_research:true
              ▼
   ┌────────────────────┐
   │ /generate          │ → drafts.cited_snippet_ids points back at sources
   │ /variations        │   exposed via /drafts/{id}/citations
   └────────────────────┘
```

## Data model

| Table                       | What it holds                                                              |
| --------------------------- | -------------------------------------------------------------------------- |
| `research_snippets`         | One row per unique `(user_id, url)`. Score, source, query, dedup primitive. |
| `research_subscriptions`    | Saved query + interval configs. `last_run_at` drives the tick scheduler.   |
| `drafts.cited_snippet_ids`  | JSON list of snippet ids that fed each draft's prompt (closes the loop).   |

Migrations live under `backend/migrations/00{2,3,4}_*.sql` — apply in order on a fresh database, or rely on SQLAlchemy `create_all` in dev.

## Endpoints

### Seeding queries

```bash
# What should I track for this product?
curl -s -X POST http://localhost:8000/research/suggest \
  -H 'content-type: application/json' \
  -d '{"product":"Fanout — agentic content studio for indie shippers","count":5}'
# → {"queries":["agentic content tools","indie hacker marketing","ai social media","content automation","developer tools launch"]}
```

### One-off fetch

```bash
curl -s -X POST http://localhost:8000/research \
  -H 'content-type: application/json' \
  -d '{
    "queries": ["agentic content tools", "indie hacker marketing"],
    "rss_feeds": ["https://news.ycombinator.com/rss"]
  }'
```

### Recurring subscriptions

```bash
# Save the config; the subscription runs autonomously
curl -s -X POST http://localhost:8000/research/subscriptions \
  -H 'content-type: application/json' \
  -d '{
    "name": "Indie launch tracker",
    "queries": ["indie hackers", "show hn launch"],
    "rss_feeds": ["https://www.indiehackers.com/feed.xml"],
    "interval_hours": 6
  }'

# Trigger your own due subscriptions manually
curl -s -X POST http://localhost:8000/research/tick

# Cron-driven fan-out across all users (requires X-Tick-Secret)
curl -s -X POST http://localhost:8000/research/tick/all \
  -H "X-Tick-Secret: ${RESEARCH_TICK_SECRET}"
```

### Generating drafts that cite signals

```bash
# Variations on a single platform
curl -s -X POST http://localhost:8000/variations \
  -H 'content-type: application/json' \
  -d '{
    "product": "Fanout — agentic content studio for indie shippers",
    "platform": "linkedin",
    "use_research": true
  }'
# → {"drafts":[{"cited_snippet_ids":["...","..."], ...}], "research_used": 8}

# See exactly which signals fed a draft
curl -s http://localhost:8000/drafts/<draft_id>/citations
# → {"draft_id":"...","snippets":[{"source":"hn","title":"...","url":"...","score":0.71}, ...]}
```

## Wiring the cron

`/research/tick/all` is the multi-user endpoint. It's gated by an `X-Tick-Secret` header that matches `RESEARCH_TICK_SECRET` in the backend env — without that env var set, the endpoint returns 403. This avoids any auth surprise: no secret, no service-auth path.

A minimum viable cron is one HTTP POST per minute. The endpoint is idempotent — subscriptions that aren't due yet are skipped — so over-polling is safe.

### GitHub Action (free)

```yaml
# .github/workflows/research-tick.yml
name: research-tick
on:
  schedule:
    - cron: "*/5 * * * *"   # every 5 min; tick is idempotent so this is safe
jobs:
  tick:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -fsS -X POST "${{ secrets.FANOUT_API_URL }}/research/tick/all" \
            -H "X-Tick-Secret: ${{ secrets.RESEARCH_TICK_SECRET }}"
```

### Vercel cron

```json
// vercel.json
{
  "crons": [
    {
      "path": "/api/research-tick",
      "schedule": "*/5 * * * *"
    }
  ]
}
```

…and have `/api/research-tick` proxy to the backend with the header.

### Render scheduled job

Set the command to:

```bash
curl -fsS -X POST "$FANOUT_API_URL/research/tick/all" -H "X-Tick-Secret: $RESEARCH_TICK_SECRET"
```

Schedule it on Render's cron tab.

## Scoring model

Each snippet's score is `(popularity × recency)^0.5` — a geometric mean so both factors must be reasonable to score well. Recency uses an exponential half-life of 48 hours (so 2-day-old content is worth half what brand-new content is). Per-source soft-max popularity:

| Source  | soft-max | Notes                                                          |
| ------- | -------- | -------------------------------------------------------------- |
| HN      | 200      | Roughly a respectable HN front-page item.                      |
| Reddit  | 500      | Communities run hotter than HN — calibrate higher.             |
| Dev.to  | 120      | Reactions are scarcer than HN points.                          |
| RSS     | n/a      | No popularity signal — recency-only, capped at 0.7 so an HN/Reddit hit can outrank a fresh RSS item. |

Comments are weighted 1.5× points/upvotes — discussion is a stronger signal than a passive vote.

## Verifying the loop

```bash
# 1. seed
curl -s -X POST http://localhost:8000/research/suggest \
  -d '{"product":"<your blurb>","count":5}' | jq '.queries'

# 2. fetch (using the suggestions)
curl -s -X POST http://localhost:8000/research \
  -d '{"queries":[...],"rss_feeds":[]}' | jq '.fetched'

# 3. confirm snippets exist + are unused
curl -s 'http://localhost:8000/research?only_unused=true' | jq 'length'

# 4. generate; check research_used > 0
curl -s -X POST http://localhost:8000/variations \
  -d '{"product":"<blurb>","platform":"linkedin","use_research":true}' | jq '.research_used'

# 5. confirm citations on the produced draft
curl -s 'http://localhost:8000/drafts/<id>/citations' | jq '.snippets | length'

# 6. confirm those snippets are now marked used (won't re-surface to the next /generate)
curl -s 'http://localhost:8000/research?only_unused=true' | jq 'length'
```

If step 6 returns the same count as step 3, the citation marking didn't run — check the backend logs for the `mark_snippets_used` call site and confirm `RESEARCH_TICK_SECRET` isn't accidentally muting the path.

## Common gotchas

- **Empty research after `/generate`.** The agent only consumes **unused** snippets. Run `/research` again or wait for the next subscription tick.
- **`UnknownPricingError` is a different module.** That's `agentbudget`. Fanout's research loop has no per-source pricing.
- **Reddit 429s under the cron.** Reddit rate-limits unauthed requests. The configured User-Agent (`fanout-research/0.1`) helps, but if you hit limits, lower your subscription `interval_hours` or shrink the query list.
- **Citations look stale.** `cited_snippet_ids` is the source of truth on each draft. The `used_in_draft_id` field on snippets is a back-compat shortcut — if you need a definitive "what fed this draft?" answer, hit `/drafts/{id}/citations`.

## Where the code lives

- `backend/app/research.py` — source fetchers, scoring, parallel orchestration
- `backend/app/store.py` — snippets + subscriptions CRUD, `top_snippets_for_agent`, `mark_snippets_used`, `get_draft_citations`
- `backend/app/main.py` — REST handlers (`/research`, `/research/suggest`, `/research/subscriptions`, `/research/tick`, `/research/tick/all`)
- `backend/app/agent.py` — `plan` / `write` / `variations` accept `research_context` and bake it into prompts
- `web/app/research/page.tsx` — workbench UI (suggest, fetch, subscriptions list)
- `web/components/CitationsPill.tsx` — the per-draft "N signals" pill
