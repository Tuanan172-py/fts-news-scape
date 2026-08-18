# Scout Report: Project Structure for Documentation Harness H1

**Date:** 2026-08-17 | **Scope:** `project/` directory | **Target:** Harness landing zone identification

## 1. docs/ Directory Tree (38 markdown files)

### design/ (14 files)
- 00-end-to-end-architecture.md — High-level system flow & data pipelines
- 01-system-overview.md — Components & responsibilities overview
- 02-execution-flow.md — Scheduler, scraper, pipeline orchestration
- 03-source-strategy.md — Data sources taxonomy (RSS, API, HTML)
- 04-sentiment-classification.md — VN sentiment lexicon & rules
- 05-notification-coverage.md — Alert/notify system design
- 06-raw-html-capture.md — Content preservation strategy
- 07-storage-layers-and-change-detection.md — Bronze/Silver/Gold schema
- 08-handoff-contract-catalog.md — API contracts & serialization
- 09-agent-io-contract.md — Agent input/output specifications
- 10-agent-orchestration-governance.md — Agent governance framework
- 11-e2e-standardization-governance.md — End-to-end standards
- 12-agent-infrastructure.md — Agent runtime & deployment
- 12-bronze-to-silver-rules.md — Transformation rules for data layers

### dev/ (6 files)
- 01-codebase-guide.md — Developer onboarding & structure
- 02-data-model-and-db.md — SQLite schema & ORM patterns
- 03-adding-a-source.md — Add new domain scraper step-by-step
- 04-testing.md — Test fixtures, pytest conventions
- 05-known-issues.md — Known bugs & workarounds
- 06-raw-html-capture-guide.md — Technical implementation detail

### domains/ (5 files)
- README.md — Domains subdirectory overview
- api-scrapers.md — CafeF, TNCK, FireAnt API details
- exchange-layer0.md — Layer-0 exchange data research
- intl-rss.md — International RSS source list
- vn-rss.md — Vietnamese RSS source list

### operations/ (2 files)
- deployment.md — Prod deployment runbook
- troubleshooting.md — Ops troubleshooting guide

### others/ (4 files)
- decisions.md — ADRs & architectural decisions
- 260726-project-approach-report.md — Phase summary (2026-07-26)
- phase1-report.md — Phase 1 completion report
- system-prompt.md — Original system prompt charter

### reference/ (3 files)
- README.md — Reference section guide
- (2 other reference docs)

### skills/ (4 files)
- cafef.md — CafeF domain-specific scraper skills
- fireant.md — FireAnt API skills & token auth
- rss-sources.md — RSS feed parsing skills
- tnck.md — TNCK domain-specific skills

### Root docs/ (5 files)
- ARCHITECTURE.md — Main architecture summary
- README.md — Docs directory index
- charter.md — Project charter (detailed)
- charter-executive-summary.md — Charter summary
- runbook.md — Operations runbook
- rss-reference.md — RSS feed reference table

## 2. plans/ Directory Structure (2 existing plans)

### Format: `YYYYMMDD-HHMM-<plan-name>/<files>`

**20260724-0859-scraping-expansion-phase1/**
- plan.md — Master plan document
- phase-01-foundation-refactor.md through phase-06-integration-hardening.md (6 phase files)
- reports/ — 01-verification-report.md
- research/ — researcher-01-frameworks-report.md, researcher-02-ops-sentiment-report.md
- scout/ — scout-01-report.md
- Structure: `<plan.md> + <phase-XX-*.md> + <reports/> + <research/> + <scout/>`

**20260725-1339-source-expansion-phase2/**
- plan.md — Master plan
- phase-01-vn-rss-sources.md through phase-04-layer0-ctck-research.md (4 phase files)
- reports/ — 01-live-verification-report.md, 02-layer0-ctck-probe.md, 03-completion-report.md
- research/ — researcher-01-vn-official-press-report.md
- Structure: Same as Phase 1

## 3. Top-Level project/ Layout

| Directory | Count | Purpose |
|-----------|-------|---------|
| config/ | 29 files | YAML domain configs, settings, secrets |
| src/ | 161 files | Core Python code: scrapers, pipeline, DB, monitor |
| scripts/ | 18 files | CLI utilities: run_once, verify_quality, watch_24h |
| tests/ | 96 files | pytest fixtures, integration tests |
| data/ | 595 files | SQLite monocle.db + JSON silver layer |
| thamkhao/ | 20 files | Research assets (reverse-eng, API specs) |
| docs/ | 38 files | Documentation (architecture, dev, ops, skills) |
| plans/ | 2 dirs | Phase 1 & Phase 2 implementation plans |

## 4. Harness Preconditions

**Checked at project root:**
- AGENTS.md — ABSENT
- CLAUDE.md — ABSENT
- docs/GLOSSARY.md — ABSENT
- docs/HARNESS.md — ABSENT
- docs/templates/ — ABSENT
- harness.db — ABSENT
- docs/stories/ — ABSENT
- docs/decisions/ — EXISTS (docs/others/decisions.md only)

**Existing meta-level docs:**
- docs/charter.md (13.3KB) — Full charter
- docs/others/system-prompt.md (3.4KB) — Original prompt
- docs/ARCHITECTURE.md — System architecture
- docs/README.md — Docs index
- plans/ structure established with scout/research/reports subdirs

## 5. Harness H1 Landing Zone Recommendation

**Primary recommendation: `project/docs/` (preferred)**
- Rationale: Existing design/ dev/ domains/ ops/ skills/ organization already established
- All meta-level docs (charter, architecture, decisions) reside here
- Pattern follows codebase structure (design → implementation)
- Existing template: docs/README.md index pattern

**Harness H1 files should land:**
```
project/docs/
├── harness/              [NEW] Harness H1 operating-model docs
│   ├── HARNESS.md        Operating model overview
│   ├── GLOSSARY.md       Terminology & domain lexicon
│   ├── AGENTS.md         Agent & role definitions
│   ├── templates/        Markdown templates (stories, ADRs, etc)
│   └── stories/          User stories & narrative docs
├── design/               [EXISTING] 14 design docs
├── dev/                  [EXISTING] 6 dev docs
├── domains/              [EXISTING] 5 domain docs
├── operations/           [EXISTING] 2 ops docs
├── skills/               [EXISTING] 4 skill docs
└── ...                   [EXISTING] Reference, others, root level
```

**Alternative (secondary):** `project/harness/` at root
- Use if intent is cross-repo harness
- Requires project-level CLAUDE.md override
- Not recommended given existing docs/ structure

## 6. Unresolved Questions

1. Should harness include agent prompt templates for news-scape-specific agents (e.g., domain-expert, sentiment-classifier)?
2. Will stories/ contain user epics, use-case narratives, or discovery docs?
3. Should AGENTS.md define project-specific agents or reference global ClaudeKit agents?
4. Will GLOSSARY.md include domain-specific terms (e.g., "Silver layer", "CafeF", "sentiment rule")?

---

**Report generated by Scout agent** | **Next step:** `HARNESS.md` + template framework instantiation
