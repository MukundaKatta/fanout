-- Eva operator: each autonomous draft-generation cycle gets one log row.
-- Lets us replay "what did the operator pick on 2026-05-24?" and rank model
-- versions / weighting strategies against each other later.

CREATE TABLE IF NOT EXISTS operator_runs (
  id                       UUID PRIMARY KEY,
  user_id                  TEXT NOT NULL,

  product                  TEXT NOT NULL,
  platforms                JSONB NOT NULL,           -- list of platform ids
  cited_snippet_ids        JSONB,                    -- snippets fed to the agent
  draft_ids                JSONB,                    -- drafts produced
  weight_by_leaderboard    BOOLEAN NOT NULL DEFAULT TRUE,
  leaderboard_metric       TEXT NOT NULL DEFAULT 'likes',

  status                   TEXT NOT NULL DEFAULT 'pending',  -- pending|ok|failed
  error                    TEXT,
  notes                    TEXT,

  started_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at             TIMESTAMPTZ,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_operator_runs_user_started ON operator_runs (user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_operator_runs_user_status  ON operator_runs (user_id, status);
