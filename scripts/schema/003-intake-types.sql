-- 003-intake-types.sql — Mở rộng CHECK constraint cho intake.input_type (Backlog #8)
-- Cho phép đủ 9 loại: new_spec, spec_slice, change_request, new_initiative, maintenance, harness_improvement, qa_inquiry, diagnostic, exploration

PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS intake_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  input_type TEXT NOT NULL
    CHECK (input_type IN ('new_spec', 'spec_slice', 'change_request', 'new_initiative', 'maintenance', 'harness_improvement', 'qa_inquiry', 'diagnostic', 'exploration')),
  summary TEXT NOT NULL,
  risk_lane TEXT NOT NULL
    CHECK (risk_lane IN ('tiny', 'normal', 'high-risk')),
  risk_flags TEXT NOT NULL DEFAULT '[]',
  story_id TEXT,
  created_at TEXT NOT NULL
);

INSERT INTO intake_new SELECT * FROM intake;

DROP TABLE intake;

ALTER TABLE intake_new RENAME TO intake;

CREATE INDEX IF NOT EXISTS idx_intake_lane ON intake(risk_lane);

PRAGMA foreign_keys = ON;
