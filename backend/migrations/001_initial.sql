-- Initial schema for Fanout. Run via psql or paste into Supabase SQL editor.
-- (App also runs Base.metadata.create_all() at startup, so this is for reference / RLS setup.)

CREATE TABLE IF NOT EXISTS drafts (
  id            TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL,
  platform      VARCHAR(32) NOT NULL,
  product       TEXT NOT NULL,
  content       TEXT NOT NULL,
  feedback      TEXT,
  plan          JSONB,
  status        VARCHAR(16) NOT NULL DEFAULT 'pending',
  scheduled_at  TIMESTAMPTZ,
  post_url      TEXT,
  error         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_drafts_user_id ON drafts (user_id);
CREATE INDEX IF NOT EXISTS ix_drafts_status ON drafts (status);
CREATE INDEX IF NOT EXISTS ix_drafts_user_status_sched
  ON drafts (user_id, status, scheduled_at);

-- Optional Supabase RLS (recommended if you ever expose Postgres directly to clients):
-- ALTER TABLE drafts ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY drafts_owner ON drafts
--   USING (user_id::uuid = auth.uid())
--   WITH CHECK (user_id::uuid = auth.uid());
