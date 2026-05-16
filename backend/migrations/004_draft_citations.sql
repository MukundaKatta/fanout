-- Add citation tracking to drafts: which research snippets fed into each draft.
-- Stored as JSONB list of snippet ids rather than a join table so a single
-- SELECT renders the draft + its citations without an extra round-trip.

ALTER TABLE drafts
  ADD COLUMN IF NOT EXISTS cited_snippet_ids JSONB;
