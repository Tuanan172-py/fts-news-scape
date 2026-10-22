# TOOL_REGISTRY.md — Tool Manifest and Degrade Ladder (H4)

This document lists the execution tools of News-Scape, their health checks and the **degrade-don't-fail** fallback when a tool is missing. Python commands use the venv `C:\venvs\news-scape` (ADR-0024).

---

## 1. Core tools manifest

| Tool ID | Tool | Purpose | Health check | Fallback (degrade ladder) |
|:---|:---|:---|:---|:---|
| `python` | Python runtime (venv `C:\venvs\news-scape`) | Pipelines, scripts, CLIs | `python --version` | **Hard stop** (required). |
| `pytest` | Pytest | Unit and integration tests | `python -m pytest --version` | Run by hand with `python -m unittest`. |
| `sqlite3` | SQLite engine (WAL mode) | `monocle.db` and `harness.db` | `python -c "import sqlite3; print(sqlite3.sqlite_version)"` | **Hard stop** (required by the durable layer). |
| `trafilatura` | Web content extractor | Article extraction (`src/processor/extractor.py`) | `python -c "import trafilatura"` | Falls back to BeautifulSoup `get_text` (`extract_text`). |
| `rapidfuzz` | String similarity matcher | Listed in `project/requirements.txt`; no module in `project/src` imports it (near-duplicate detection uses SimHash, `src/pipeline/run.py`) | `python -c "import rapidfuzz"` | None needed. |
| `git` | Git | Version control, working tree | `git --version` | **Hard stop** (required by codebase governance). |
| `audit_codebase` | Codebase and git auditor | AST, OneDrive conflicts, git hygiene | `python project/scripts/maintenance/audit_codebase.py` | Fall back to `python scripts/harness_cli.py audit` without `--codebase`. |

---

## 2. Degrade-don't-fail principles

1. When a non-essential tool is missing or fails, the system logs a warning and degrades to the fallback; it **MUST NOT** crash the whole pipeline.
2. Every tool degradation is recorded in the `intervention` or `backlog` table for follow-up.
