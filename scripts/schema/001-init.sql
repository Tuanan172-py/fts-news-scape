-- 001-init.sql — Durable Layer schema v1 for News-Scape Harness (H2-H5)
-- Conforms to the reference architecture in other/harness/HARNESS_BUILD_FROM_SCRATCH_VI.md

PRAGMA foreign_keys = ON;

-- 1. Schema migration version tracking
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL,
  description TEXT
);

-- 2. Story table (The heart of execution & proof)
CREATE TABLE IF NOT EXISTS story (
  id TEXT PRIMARY KEY,                       -- e.g. 'US-001'
  title TEXT NOT NULL,
  parent_epic TEXT,
  status TEXT NOT NULL DEFAULT 'planned'     -- planned | in_progress | implemented | changed | retired | blocked | deferred
    CHECK (status IN ('planned', 'in_progress', 'implemented', 'changed', 'retired', 'blocked', 'deferred')),
  lane TEXT NOT NULL DEFAULT 'normal'        -- tiny | normal | high-risk
    CHECK (lane IN ('tiny', 'normal', 'high-risk')),
  product_contract TEXT,
  acceptance_criteria TEXT,
  unit_proof INTEGER NOT NULL DEFAULT 0,     -- 0 = not passed / 1 = passed
  integration_proof INTEGER NOT NULL DEFAULT 0,
  e2e_proof INTEGER NOT NULL DEFAULT 0,
  platform_proof INTEGER NOT NULL DEFAULT 0,
  verify_command TEXT,
  evidence TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_story_status ON story(status);
CREATE INDEX IF NOT EXISTS idx_story_lane ON story(lane);

-- 3. Intake table (Request classification)
CREATE TABLE IF NOT EXISTS intake (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  input_type TEXT NOT NULL                   -- new_spec | spec_slice | change_request | new_initiative | maintenance | harness_improvement
    CHECK (input_type IN ('new_spec', 'spec_slice', 'change_request', 'new_initiative', 'maintenance', 'harness_improvement')),
  summary TEXT NOT NULL,
  risk_lane TEXT NOT NULL                    -- tiny | normal | high-risk
    CHECK (risk_lane IN ('tiny', 'normal', 'high-risk')),
  risk_flags TEXT NOT NULL DEFAULT '[]',     -- JSON array of matched risk flags
  story_id TEXT,                             -- Soft link to story.id
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intake_lane ON intake(risk_lane);

-- 4. Decision table (ADR records)
CREATE TABLE IF NOT EXISTS decision (
  id TEXT PRIMARY KEY,                       -- e.g. '0001-harness-first-approach'
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'accepted'    -- proposed | accepted | superseded | rejected
    CHECK (status IN ('proposed', 'accepted', 'superseded', 'rejected')),
  doc_path TEXT NOT NULL,
  predicted_impact TEXT,
  actual_outcome TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decision_status ON decision(status);

-- 5. Backlog table (Friction reservoir & self-improvement)
CREATE TABLE IF NOT EXISTS backlog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  discovered_while TEXT,
  current_pain TEXT NOT NULL,
  suggested_improvement TEXT,
  risk_lane TEXT NOT NULL DEFAULT 'normal'
    CHECK (risk_lane IN ('tiny', 'normal', 'high-risk')),
  status TEXT NOT NULL DEFAULT 'open'        -- open | in_progress | resolved | dismissed
    CHECK (status IN ('open', 'in_progress', 'resolved', 'dismissed')),
  component TEXT,                            -- e.g. 'task_spec', 'context', 'verification', 'durable'
  outcome TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_backlog_status ON backlog(status);
CREATE INDEX IF NOT EXISTS idx_backlog_component ON backlog(component);

-- 6. Trace table (Active Observability per execution)
CREATE TABLE IF NOT EXISTS trace (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  story_id TEXT,
  intake_id INTEGER,
  task_summary TEXT NOT NULL,
  actions_taken TEXT NOT NULL DEFAULT '[]',  -- JSON array
  files_read TEXT NOT NULL DEFAULT '[]',     -- JSON array
  files_changed TEXT NOT NULL DEFAULT '[]',  -- JSON array
  outcome TEXT NOT NULL                      -- completed | blocked | failed | partial
    CHECK (outcome IN ('completed', 'blocked', 'failed', 'partial')),
  score_context REAL DEFAULT 1.0,            -- 0.0 to 1.0 context compliance score
  score_trace REAL DEFAULT 1.0,              -- 0.0 to 1.0 trace completeness score
  friction TEXT,
  error_msg TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (story_id) REFERENCES story(id) ON DELETE SET NULL,
  FOREIGN KEY (intake_id) REFERENCES intake(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_trace_story ON trace(story_id);
CREATE INDEX IF NOT EXISTS idx_trace_outcome ON trace(outcome);

-- 7. Intervention table (Session error & human/agent intervention log)
CREATE TABLE IF NOT EXISTS intervention (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id INTEGER,
  story_id TEXT,
  reason TEXT NOT NULL,
  corrective_action TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (trace_id) REFERENCES trace(id) ON DELETE CASCADE
);

-- 8. Tool Registry table (Tool manifest & degrade ladder)
CREATE TABLE IF NOT EXISTS tool (
  id TEXT PRIMARY KEY,                       -- e.g. 'pytest', 'trafilatura', 'sqlite3'
  name TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'active'      -- active | degraded | missing
    CHECK (status IN ('active', 'degraded', 'missing')),
  degrade_fallback TEXT,
  last_verified_at TEXT
);
