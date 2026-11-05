-- Lock Fanout tables away from Supabase's public Data API (PostgREST).
--
-- When DATABASE_URL points at a Supabase project, every table in the
-- ``public`` schema is reachable at https://<project>.supabase.co/rest/v1/
-- with the *anon* key — which ships in the web bundle as
-- NEXT_PUBLIC_SUPABASE_ANON_KEY. Without RLS, anyone could read or modify
-- every user's drafts, snippets, subscriptions and outcomes, bypassing the
-- FastAPI authz layer entirely.
--
-- The backend connects as the table owner (``postgres``), which bypasses
-- RLS, so enabling RLS with **no policies** denies the anon/authenticated
-- API roles while leaving the backend untouched. Safe to run on plain
-- Postgres too (the REVOKEs are skipped when the Supabase roles don't exist).
-- Idempotent.

ALTER TABLE IF EXISTS drafts                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS research_snippets      ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS research_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS draft_outcomes         ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS operator_runs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS operator_subscriptions ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format(
        'REVOKE ALL ON drafts, research_snippets, research_subscriptions, '
        'draft_outcomes, operator_runs, operator_subscriptions FROM %I', r);
    END IF;
  END LOOP;
END
$$;
