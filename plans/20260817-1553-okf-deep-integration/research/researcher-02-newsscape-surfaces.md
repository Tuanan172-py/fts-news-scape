# OKF Deep Integration — News-Scape Surfaces Research

**Date:** 2026-08-17 | **Status:** Complete | **Scope:** Config/schema/agent/harness boundaries.

---

## 1. Domain YAML Schema & Loader

### Schema Structure (per cafef.yaml)
```yaml
name: cafef                    # Required: domain identifier
enabled: true                  # Optional (default: true)
method: [api|rss|html]        # Required
rate_limit: 3.0               # Optional (default: 3.0)
timeout: 30                    # Optional (default: 30)
api:                          # If method=api
  endpoint: "https://..."
  http_method: GET
  params: {Newstype: 0, PageSize: 20, ...}
  headers: {Referer, ...}
detail:                       # Optional detail-fetch config
  content_selector: "div#mainContent"
  max_details_per_cycle: 30
capture:
  raw_dir: "data/raw_html"
  min_body_bytes: 2048       # Completeness check threshold
compliance:
  respect_robots: true
  proxy_rotation: false
  proxies: []
pitfalls: "string (free-text notes)"
```

### Loader Mechanism (config.py §load_domain_config)
- **Path:** `project/config/domains/<name>.yaml` → `yaml.safe_load()` (PyYAML)
- **Validation:** Hard-enforces `name` + `method` keys; defaults `enabled=True`, `rate_limit=3.0`, `timeout=30`
- **Merge:** Settings deep-merged via `_deep_merge()` (dict recursion, override wins)
- **Discovery:** `list_domains()` globs `*.yaml`, filters enabled-only
- **23 existing YAMLs** ✓ (cafef, tnck, fireant, vietstock, vnexpress, vneconomy, etc.)

### Recommend: **GENERATE** (backward-compat)
- OKF frontmatter → YAML generator appends new domains to `config/domains/` without mutating existing 23.
- **Validation-only** for existing YAMLs (read-only, no auto-update) unless drift detected → alert.
- Schema drift check: OKF spec top-level keys vs. hard-enforced `{name, method}` → OK; optional keys stay backward-compat.

---

## 2. Articles Table DDL & Drift-Check Target

**Source:** `project/src/db/store.py` §_SCHEMA (lines 41–147).

### `articles` Table (Primary)
```sql
CREATE TABLE articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  url_title_hash TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  summary TEXT,
  content_html TEXT,
  content_text TEXT,
  published_at TEXT,
  author TEXT,
  source_domain TEXT NOT NULL,
  symbols TEXT,                 -- comma-sep or JSON array
  categories TEXT,              -- comma-sep or JSON array
  sentiment TEXT,               -- {positive|neutral|negative}
  sentiment_score REAL,         -- [-1.0, 1.0]
  fetched_at TEXT NOT NULL,     -- ISO 8601 timestamp (VN TZ)
  processed_at TEXT,            -- ISO 8601
  metadata_json TEXT            -- arbitrary JSON blob
);
```

### Supporting Tables (drift-detection infrastructure)
- **`article_versions`** (15 cols): track content_sha256, simhash64, selector_drift, state {OK|SELECTOR_BROKEN|TEMPLATE_DRIFT}
- **`work_items`** (13 cols): article→agent handoff queue (status: pending|claimed|done|failed|held)
- **`agent_outputs`** (11 cols): agent deliverables + dod_pass flag (idempotency on article_id+raw_sha256)
- **`seen_articles`**, **`scraper_heartbeat`**, **`scraper_metrics`**, **`pipeline_state`**: supporting telemetry.

### Drift-Check Strategy
- **Pre-commit hook:** OKF `tables/articles.md` schema ↔ _SCHEMA DDL comparison (column names, types, constraints).
- **Target:** Ensure `articles` columns match; new columns appended backward-compatible (NOT added mid-table).
- **Failing case:** OKF spec removes `metadata_json` → drift detected, block commit, alert GĐ2.

---

## 3. Existing JSON-Schema & Lifecycle Conventions

### Schemas Inventory
- **`work-package-v1.schema.json`**: input contract for agent task-packet (article_id, raw_html_path, cleaned_text, citations, etc.)
- **`agent-output-v1.schema.json`**: output contract agent must satisfy (confidence, citations, extraction_quality, processing_metadata)
- **`silver-v1.schema.json`**: (derived/enriched article format)
- **`task-lifecycle-v1.yaml`** (referenced in dod.py §29–41): thresholds enum (confidence_min=0.65, min_citations=2, quality_ok=[high,medium])

### DoD Predicates (5-predicate checklist in dod.py)
1. **schema_valid** (hard): `validate(agent_output, 'agent-output-v1')` via contract_validator
2. **confident**: `confidence ≥ confidence_min` (default 0.65)
3. **grounded**: citations ≥ min_citations (default 2); each citation.source_span ⊂ cleaned_text
4. **quality_ok**: extraction_quality ∈ {high, medium}
5. **auditable**: processing_metadata ⊃ {agent_provider, model_used, timestamp}

### OKF Alignment
- JSON-schema convention is **production-grade** (hard validation, not soft).
- **DoD YAML approach** (thresholds overridable per task-lifecycle-v1.yaml) mirrors OKF "read thresholds from charter" pattern.
- OKF charter → `thresholds` section → `dod.py` read at DoD-check time (fallback hardcoded defaults).

---

## 4. Harness Story & DoD Template (Phase 02 Status)

**Source:** `plans/20260817-1536-harness-h1-newsscape/phase-02-templates-scaffolding.md` (lines 1–87).

### Template Locations (Phase 02 Planned)
- `docs/templates/story.md` — must include `Parent / Epic: ` free-text field + 4-tier Validation table (Unit/Integration/E2E/Platform)
- `docs/templates/decision.md` — ADR structure (Context/Decision/Alternatives/Consequences/Follow-Up)
- `docs/templates/validation-report.md` — Results table (defaults "not run")
- `docs/HARNESS_BACKLOG.md` — friction reservoir (Title/Discovered While/Pain/Improvement/Risk/Status)
- Empty `docs/stories/`, `docs/decisions/` dirs (.gitkeep)

### **OKF Updates Required Checklist** (to inject into story.md template)
**Add after "Validation" table:**
```markdown
## OKF Charter Readiness
- [ ] Charter exists at `plans/YYYYMMDD-HHMM-okf-<epic>/charter.md`
- [ ] `tables/articles.md` schema matches `project/src/db/store.py` DDL (no drift)
- [ ] Domain YAML config valid (name, method required) if new source added
- [ ] Agent-output schema compatible with `schemas/agent-output-v1.schema.json`
- [ ] DoD thresholds documented in charter or linked to `task-lifecycle-v1.yaml`
```

### H2 Climb Signals (Infrastructure Readiness)
- **CLI:** `python -m src.agent.runner --export-tasks | --ingest-output <file>`
- **SQLite:** `agent_outputs` table + `work_items` status {pending|claimed|done|failed|held}
- **CONTEXT_RULES:** (Charter § TBD — not yet defined; suggest "agent reads OKF charter read-only, generates task-packet based on work_package-v1 schema")
- **TRACE_SPEC:** (Audit trail: agent_outputs.processing_metadata.timestamp + dod_pass + dod_reasons logged to database)

---

## 5. Decision-Record Convention & Agent Framework

### Decision Records (ADRs)
- **Convention:** planned in Phase 02 as `docs/decisions/NNNN-<title>.md` (no existing ADRs in codebase yet).
- **Template:** Context / Decision / Alternatives / Consequences (Positive/Tradeoffs) / Follow-Up; status {Proposed|Accepted|Superseded|Rejected}.
- **OKF Integration:** Record design decisions (e.g., "confidence threshold 0.65", "when to hold vs. fail work_item") as ADRs, linked from charter §decision_records.

### Agent Framework (AgentRunner)
**Read/Write Surface:**
- **Export (producer → agent):**
  - `AgentRunner.export_tasks(limit=20, worker_id)` → claims pending work_items via `Catalog.claim()` (exactly-once) → builds task-packet → writes `data/agent_tasks/<id>.task.json` (read-only to agent)
  - **Input:** work-package-v1 schema (article_id, raw_html_path, raw_sha256, cleaned_text, citations, published_at, domain, etc.)
  
- **Ingest (agent → producer):**
  - `AgentRunner.ingest_output(output: dict|str)` → validate schema → verify_preconditions (raw_sha256 match, not SELECTOR_BROKEN/TEMPLATE_DRIFT) → check_dod (5 predicates) → `store.insert_agent_output()` → mark_done/mark_failed (idempotent on article_id+raw_sha256)
  - **Output:** agent-output-v1 schema (confidence, citations, extraction_quality, processing_metadata, ...)

- **Catalog (handoff queue):**
  - Tables: `work_items` (status, claimed_by, claimed_at, done_at, error, change_state)
  - Precondition states: `SELECTOR_BROKEN`, `TEMPLATE_DRIFT` → auto-held (never claimed)
  - **Observability:** Each ingest logs `article_id, dod_pass, dod_reasons[:3]` + writes agent_outputs row (audit trail via processing_metadata)

---

## 6. OKF ↔ Code ↔ Harness ↔ Agent Boundaries

### Read-Only Surfaces (Agent Cannot Mutate)
1. **Domain YAML config** (`project/config/domains/`) — agent reads via work-package (domain field), never writes
2. **Articles SQLite** (articles, seen_articles, scraper_heartbeat) — agent read-only (indexed views)
3. **OKF charter** (plans/YYYYMMDD-HHMM-okf-*/charter.md) — agent reads thresholds/decision_records, never updates

### Write Surfaces (Agent Ownership)
1. **agent_outputs table** — agent writes via ingest_output (populated by external agent submission, not pipeline)
2. **work_items status** — producer marks done/failed (not agent directly; Catalog.mark_* methods)
3. **Task-packet file** (`data/agent_tasks/<id>.task.json`) — producer writes, agent reads

### Harness Observability Trace
- **Producer phase** (export_tasks): logs `[agent] exported N task-packets → data/agent_tasks/`
- **Agent phase**: (external, user-controlled; logs agent_provider + model_used in processing_metadata)
- **Ingest phase** (ingest_output): logs `[agent] ingest <article_id> → dod_pass=<bool> reasons=[...]` + database insertion to agent_outputs + heartbeat
- **Query:** `SELECT article_id, dod_pass, dod_reasons FROM agent_outputs WHERE created_at > ?` for audit trail

---

## 7. Concrete Recommendations

1. **Domain Config Generation**
   - OKF → `config/domains/<name>.yaml` generator (validation-only for existing 23 domains, write-new only)
   - Skip migration; append-only strategy (YAGNI)

2. **Drift-Check Pre-Commit Hook**
   - Parse `project/src/db/store.py` _SCHEMA → extract CREATE TABLE articles columns
   - Compare vs. OKF `tables/articles.md` schema definition
   - Fail if drift detected (columns removed/renamed); warn if reordered (OK)

3. **Story Template Extension**
   - Phase 02 templates ready (planned); inject "OKF Charter Readiness" checklist before validation table
   - Link to task-lifecycle-v1.yaml for threshold overrides (already in place)

4. **Agent/Harness Boundary Spec**
   - Agent reads: work-package-v1 (task-packet), OKF charter thresholds
   - Agent writes: agent-output-v1 (via ingest_output, never direct DB)
   - Producer controls: work_items status, DoD evaluation, mark_done/mark_failed
   - Audit trail: agent_outputs.processing_metadata (immutable log)

5. **CLI Command Readiness**
   - `python -m src.agent.runner --export-tasks [--limit N] [--worker-id WORKER]`
   - `python -m src.agent.runner --ingest-output <path-to-agent-output.json>`
   - (Already scaffolded in runner.py; no LLM calls in producer)

---

## Unresolved Questions

1. **OKF Charter location**: Clarify `plans/YYYYMMDD-HHMM-okf-<epic>/charter.md` path convention; use git commit hash as idempotency key or sequential numbering (e.g., charter-v2)?
2. **Thresholds override persistence**: Should task-lifecycle-v1.yaml thresholds be per-story (inline in OKF charter) or global? Currently dod.py reads global fallback.
3. **Agent provider audit**: How to bind external agent runs (Claude, GPT, etc.) to work_item claims? Suggest agent.runner export--export-tasks write a `WORKER_ID` to task-packet, agent echoes back in processing_metadata.
4. **Precondition state diagram**: HELD states (SELECTOR_BROKEN, TEMPLATE_DRIFT) today auto-block claim; who/when triggers transition to retryable state? Requires manual drift-fix + state reset.
5. **Raw HTML archival**: work_items.package_path references work-package JSON; does raw_html_path inside it persist after agent completes? Risk of dangling references if raw data deleted (GC policy unclear).

---

**Research Complete** | Repo: C:\Users\An Thanh Pham\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape
