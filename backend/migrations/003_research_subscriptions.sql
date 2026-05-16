-- Research subscriptions — saved query configurations that run on an interval.
-- See app/research.py + main.research_tick for how this drives the autonomous loop.

CREATE TABLE IF NOT EXISTS research_subscriptions (
  id                   TEXT PRIMARY KEY,
  user_id              TEXT NOT NULL,
  name                 VARCHAR(128) NOT NULL,
  queries              JSONB NOT NULL DEFAULT '[]'::jsonb,
  rss_feeds            JSONB NOT NULL DEFAULT '[]'::jsonb,
  sources              JSONB NOT NULL DEFAULT '["hn","devto","reddit","rss"]'::jsonb,
  interval_hours       INTEGER NOT NULL DEFAULT 24,
  active               BOOLEAN NOT NULL DEFAULT TRUE,
  last_run_at          TIMESTAMPTZ,
  last_fetched_count   INTEGER,
  last_error           TEXT,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_research_subs_user_id          ON research_subscriptions (user_id);
CREATE INDEX IF NOT EXISTS ix_research_subs_active           ON research_subscriptions (active);
CREATE INDEX IF NOT EXISTS ix_research_subs_active_lastrun   ON research_subscriptions (active, last_run_at);

-- Optional Supabase RLS:
-- ALTER TABLE research_subscriptions ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY research_subs_owner ON research_subscriptions
--   USING (user_id::uuid = auth.uid())
--   WITH CHECK (user_id::uuid = auth.uid());
