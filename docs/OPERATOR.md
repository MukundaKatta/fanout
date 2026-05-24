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

## Pairing with cron

There is no built-in operator scheduler yet — drive `/operator/run` from
the same hourly cron that already runs `/research/tick/all` if you want
the loop to be fully autonomous.  Recommended sequence:

1. `/research/tick/all`   — pull fresh signals
2. `/operator/run`        — pick + draft
3. extension polls `/queue` → posts → reports outcomes

## Where the code lives

- `backend/app/operator.py` — `operator.run(uid, ...)` end-to-end driver
- `backend/app/store.py` — `select_experiment_snippets`,
  `start_operator_run`, `complete_operator_run`, `fail_operator_run`,
  `list_operator_runs`, `get_operator_run`
- `backend/app/models.py` — `OperatorRun` SQLAlchemy model
- `backend/migrations/006_operator_runs.sql`
- `backend/app/main.py` — `/operator/run`, `/operator/runs`,
  `/operator/runs/{run_id}`
- `web/lib/api.ts` — `api.operator.{run,list,get}` typed client
