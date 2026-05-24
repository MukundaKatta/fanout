# Eva operator — autonomous draft cycle

The operator is the thinnest possible layer that wraps `/generate` with
two extras:

1. **An experiment picker** that biases snippet selection toward sources
   whose past drafts have produced engagement.  Cold-start safe — falls
   back to plain score-desc when no leaderboard signal exists.
2. **An audit row** (`operator_runs`) for every cycle so we can replay
   what was picked and how it performed later.

Think of it as the "press a button, get a fully grounded slate of
platform drafts" surface.  Everything it does is also available via the
manual `/generate` path; the operator just chains them together with the
weighting and the log.

## The cycle

```
   /operator/run
        │
        ▼
   select_experiment_snippets(uid, limit, weight_by_leaderboard)
        │   ├─ unused snippets, score-desc
        │   └─ +leaderboard boost (source, query) → total of top winner
        ▼
   format_for_prompt(snippets) ─► SocialAgent.run(product, platforms, research)
        │
        ▼
   save_drafts(uid, product, result, cited_snippet_ids=...)
        │
        ▼
   mark_snippets_used(...)
        │
        ▼
   complete_operator_run(run_id, cited_snippet_ids, draft_ids, notes)
```

If anything raises, the run row lands in `failed` status with the
exception class + message captured — no row ever stays `pending`.

## Endpoints

```bash
# one autonomous cycle, all platforms, leaderboard-weighted
curl -s -X POST http://localhost:8000/operator/run \
  -H 'content-type: application/json' \
  -d '{"product":"Fanout — agentic content studio for indie shippers","platforms":["x","linkedin"]}'
# → {"operator_run_id":"...","plan":{...},"drafts":[...],
#    "picked_snippets":[...],"leaderboard_used":false,"winning_sources":[]}

# audit trail (newest first)
curl -s 'http://localhost:8000/operator/runs?limit=20' | jq

# one specific run
curl -s 'http://localhost:8000/operator/runs/<run_id>' | jq
```

## Weighting

- `weight_by_leaderboard` (default `true`).  When false, the picker uses
  the same ordering as the manual workbench — `top_snippets_for_agent`
  → unused, sorted by `score`.
- `leaderboard_metric` (default `"likes"`) — pick a different metric
  (e.g. `"comments"` or `"shares"`) to bias against engagement quality
  instead of raw reach.
- Cold-start: with no `draft_outcomes` rows yet, the picker silently
  falls back to score-only.  `leaderboard_used` in the response is
  `false` so the caller can tell which mode ran.

## The notes field

Every completed run carries a one-line `notes` string suitable for
showing in a UI:

- `"leaderboard-weighted; 5 snippets fed 4 drafts. winners: hn/agents, reddit/agents, ..."`
- `"cold-start (no leaderboard yet); 5 top-score snippets fed 4 drafts"`
- `"cold-start (no banked snippets); 4 drafts produced ungrounded"`

## Operator subscriptions (autonomous mode)

For the loop to be truly autonomous you don't want to hand-roll a cron
that calls `/operator/run` — you want stored configs that the backend
walks on a cadence, the same way research subscriptions work.  That is
`operator_subscriptions`.

### Shape

Each subscription is `(name, product, platforms, interval_hours,
weight_by_leaderboard, leaderboard_metric, snippet_limit, active)`.
`last_run_at` gates the cron so a sub only fires when
`now - last_run_at >= interval_hours`; a freshly-created sub with
`last_run_at = NULL` is considered due immediately.

### Endpoints

```bash
# CRUD
curl -s -X POST  http://localhost:8000/operator/subscriptions \
     -d '{"name":"daily-x-linkedin","product":"<blurb>","platforms":["x","linkedin"]}'
curl -s          http://localhost:8000/operator/subscriptions
curl -s -X PATCH http://localhost:8000/operator/subscriptions/<id> -d '{"active":false}'
curl -s -X DELETE http://localhost:8000/operator/subscriptions/<id>

# Manual fire — runs every sub belonging to the authed user that is due now
curl -s -X POST http://localhost:8000/operator/tick

# Service-auth fan-out — used by the hourly GitHub Action; off by default
curl -s -X POST http://localhost:8000/operator/tick/all \
     -H "X-Tick-Secret: $OPERATOR_TICK_SECRET"
```

### Cron wiring

`.github/workflows/operator-tick.yml` is the recommended driver.  It is
off by default; turn it on by setting:

```
REPO VARIABLE  OPERATOR_TICK_ENABLED = "true"
REPO SECRET    OPERATOR_TICK_URL     = "https://api.example.com/operator/tick/all"
REPO SECRET    OPERATOR_TICK_SECRET  = "<same value as backend env>"
```

The workflow hits `/operator/tick/all` hourly (minute :37, deliberately
offset from research-tick at :17 so they don't fight for backend
attention).  Failures log a warning and exit 0 — a flaky backend should
not redden the repo's CI badge.

### Error isolation

`tick_all` walks every due subscription in sequence.  A subscription
that raises mid-cycle gets its `last_error` stamped, but the remaining
subscriptions in the batch still run — one broken product blurb cannot
silence the whole fleet.

## Pairing with cron

Recommended sequence on a single host:

1. `/research/tick/all`   — pull fresh signals (`:17 * * * *`)
2. `/operator/tick/all`   — pick + draft per subscription (`:37 * * * *`)
3. extension polls `/queue` → posts → reports outcomes

## Where the code lives

- `backend/app/operator.py` — `operator.run(uid, ...)` end-to-end driver,
  `operator.tick_user(uid)`, `operator.tick_all()`
- `backend/app/store.py` — `select_experiment_snippets`,
  `start_operator_run`, `complete_operator_run`, `fail_operator_run`,
  `list_operator_runs`, `get_operator_run`, plus subscription CRUD
  (`create_operator_subscription`, `list_operator_subscriptions`,
  `update_operator_subscription`, `delete_operator_subscription`,
  `due_operator_subscriptions`, `mark_operator_subscription_run`)
- `backend/app/models.py` — `OperatorRun` + `OperatorSubscription`
- `backend/migrations/006_operator_runs.sql`,
  `backend/migrations/007_operator_subscriptions.sql`
- `backend/app/main.py` — `/operator/run`, `/operator/runs`,
  `/operator/runs/{run_id}`, `/operator/subscriptions` CRUD,
  `/operator/tick`, `/operator/tick/all`
- `.github/workflows/operator-tick.yml` — hourly cron driver
- `web/lib/api.ts` — `api.operator.{run,list,get}`,
  `api.operator.subscriptions.{list,create,update,remove}`,
  `api.operator.tick()`
