-- 002-agent-metrics.sql — Spine 3: Per-Agent KPI Ledger (AGENT_NETWORK_DESIGN.md)
-- Đo lường hiệu năng từng cognitive agent để nuôi vòng tự cải tiến (propose).
-- Tách biệt hoàn toàn với CSDL nghiệp vụ monocle.db; nằm trong harness.db.

-- 9. Agent Metrics table (Per-agent KPI ledger for self-improvement loop)
CREATE TABLE IF NOT EXISTS agent_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id   TEXT NOT NULL,                 -- khớp registry.yaml agents[].id
  run_ts     TEXT NOT NULL,                 -- ISO timestamp thời điểm ghi nhận đợt
  items      INTEGER NOT NULL DEFAULT 0,    -- số bài xử lý trong đợt
  dod_pass   INTEGER NOT NULL DEFAULT 0,    -- số bài đạt DoD
  dod_total  INTEGER NOT NULL DEFAULT 0,    -- số bài chấm DoD (mẫu số dod_pass_rate)
  tokens     INTEGER,                       -- token tiêu thụ đợt (NULL cho operator 0-token)
  fp_flags   INTEGER NOT NULL DEFAULT 0,    -- cờ nghi ngờ (vd citations copy vào key_points)
  wave       TEXT,                          -- nhãn đợt/batch (vd 'wave1', 'batch_03')
  note       TEXT,                          -- ghi chú RCA ngắn
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_metrics_agent ON agent_metrics(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_metrics_ts ON agent_metrics(run_ts);
