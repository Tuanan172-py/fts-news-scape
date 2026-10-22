# HARNESS_AUDIT.md — Entropy and Process Drift Audit (H5)

This document defines the automatic scan that detects process drift and entropy in the harness. The implementation is `cmd_audit` in `scripts/harness_cli.py`.

---

## 1. Drift checks

`python scripts/harness_cli.py audit` (add `--codebase` for the hygiene check) scans:

| # | Check | Description and risk | Penalty |
|:---|:---|:---|:---:|
| **1** | **Unproven implemented stories** | A story is `implemented` but every proof column (`unit`, `integ`, `e2e`, `platform`) is 0. | $-0.20$ / story |
| **2** | **WIP = 1 violation** | More than one `in_progress` story declares the same `branch` (ADR-0022). | $-0.25$ |
| **3** | **Missing traces** | A story is `implemented` or `blocked` but has no row in the `trace` table. | $-0.10$ / story |
| **4** | **Backlog accumulation** | More than 5 friction items are `open`. | $-0.15$ |
| **5** | **High-risk without intake** | A `high-risk` story has no linked intake row (the hard-gate record). | $-0.15$ / story |
| **6** | **Schema health** | Reports the `harness.db` schema version applied from `scripts/schema/*.sql`. | Reported, no penalty |
| **7** | **Knowledge contract** | `doc lint` findings over governed documents (ADR-0021, codes in `docs/knowledge/README.md` §4). | $-0.02$ / finding, at most $-0.30$ |
| **8** | **Codebase and git hygiene** | With `--codebase`, runs `project/scripts/maintenance/audit_codebase.py`: AST errors, OneDrive conflict files (`-HOSTNAME`), forbidden tracked files. | AST error: $-0.25$<br/>Forbidden tracked file: $-0.20$<br/>OneDrive conflict: $-0.15$ |

---

## 2. Health and entropy score

$$\text{Health Score} = \max\Big(0.0, \, 1.0 - \sum \text{Penalties}\Big)$$
$$\text{Entropy Score} = 1.0 - \text{Health Score}$$

* **Health Score $\ge 0.85$:** healthy, discipline holds.
* **Health Score $0.50 – 0.84$:** process drift; clean up traces and proof.
* **Health Score $< 0.50$:** severe decay; start a harness re-alignment.
