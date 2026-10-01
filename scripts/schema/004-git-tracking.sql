-- 004-git-tracking.sql — Bổ sung theo dõi Git commit và branch vào story và trace (US-030)

ALTER TABLE story ADD COLUMN git_commit TEXT;
ALTER TABLE story ADD COLUMN git_branch TEXT;

ALTER TABLE trace ADD COLUMN git_commit TEXT;
ALTER TABLE trace ADD COLUMN git_branch TEXT;
