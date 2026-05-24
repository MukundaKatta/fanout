-- Operator subscriptions: stored configs that drive autonomous draft cycles.
-- Paired with the /operator/tick endpoint and the hourly GitHub Action so a
-- user can wire one product blurb + a platform list once and the operator
-- will produce drafts on a cadence.

CREATE TABLE IF NOT EXISTS operator_subscriptions (
  id                       UUID PRIMARY KEY,
  user_id                  TEXT NOT NULL,

  name                     TEXT NOT NULL,
  product                  TEXT NOT NULL,                         -- the blurb fed into /generate
  platforms                JSONB NOT NULL DEFAULT '[]'::jsonb,
  weight_by_leaderboard    BOOLEAN NOT NULL DEFAULT TRUE,
  leaderboard_metric       TEXT NOT NULL DEFAULT 'likes',
  snippet_limit            INTEGER NOT NULL DEFAULT 8,

  interval_hours           INTEGER NOT NULL DEFAULT 24,           -- bounded server-side
  active                   BOOLEAN NOT NULL DEFAULT TRUE,

  last_run_at              TIMESTAMPTZ,
  last_run_id              TEXT,                                  -- operator_runs.id of the most recent cycle
  last_error               TEXT,

  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_opsubs_user            ON operator_subscriptions (user_id);
CREATE INDEX IF NOT EXISTS ix_opsubs_active_lastrun  ON operator_subscriptions (active, last_run_at);
