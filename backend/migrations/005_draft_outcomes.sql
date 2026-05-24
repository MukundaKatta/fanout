-- Outcome feedback: engagement metrics that come back AFTER a draft is posted.
-- Lets the research loop self-tune: if a source's snippets ground drafts that
-- consistently get more engagement, we surface them more aggressively next time.
--
-- Append-only by design (no UPDATE / DELETE on existing rows) so we can replay
-- the metric timeline if the ranking model changes.

CREATE TABLE IF NOT EXISTS draft_outcomes (
  id              UUID PRIMARY KEY,
  user_id         TEXT NOT NULL,
  draft_id        TEXT NOT NULL,
  platform        TEXT NOT NULL,
  metric_kind     TEXT NOT NULL,          -- likes | comments | views | reposts | clicks | shares | replies
  metric_value    INTEGER NOT NULL,
  post_url        TEXT,
  observed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_outcomes_draft        ON draft_outcomes (draft_id);
CREATE INDEX IF NOT EXISTS ix_outcomes_user_seen    ON draft_outcomes (user_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS ix_outcomes_user_kind    ON draft_outcomes (user_id, metric_kind, observed_at DESC);
