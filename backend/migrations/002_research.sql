-- Research snippets: persisted signals that feed the agent's planning step.
-- See backend/app/research.py for the source list (HN, Dev.to, Reddit, RSS).

CREATE TABLE IF NOT EXISTS research_snippets (
  id                 TEXT PRIMARY KEY,
  user_id            TEXT NOT NULL,
  source             VARCHAR(32) NOT NULL,
  query              VARCHAR(256),
  url                TEXT NOT NULL,
  title              TEXT NOT NULL,
  snippet            TEXT,
  author             VARCHAR(128),
  score              DOUBLE PRECISION NOT NULL DEFAULT 0,
  published_at       TIMESTAMPTZ,
  used_in_draft_id   TEXT,
  extra              JSONB,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Same URL ingested twice for the same user collapses to one row —
  -- this is the dedup primitive the research loop relies on.
  CONSTRAINT uq_research_user_url UNIQUE (user_id, url)
);

CREATE INDEX IF NOT EXISTS ix_research_user_id     ON research_snippets (user_id);
CREATE INDEX IF NOT EXISTS ix_research_source      ON research_snippets (source);
CREATE INDEX IF NOT EXISTS ix_research_query       ON research_snippets (query);
CREATE INDEX IF NOT EXISTS ix_research_used_draft  ON research_snippets (used_in_draft_id);
CREATE INDEX IF NOT EXISTS ix_research_user_score  ON research_snippets (user_id, score);

-- Optional Supabase RLS if you ever expose Postgres directly to clients:
-- ALTER TABLE research_snippets ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY research_owner ON research_snippets
--   USING (user_id::uuid = auth.uid())
--   WITH CHECK (user_id::uuid = auth.uid());
