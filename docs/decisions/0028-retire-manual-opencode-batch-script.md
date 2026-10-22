---
id: ADR-0028
type: adr
title: Retire the manual opencode batch script from the runner order
status: accepted
lane: normal
created: 2026-10-22
updated: 2026-10-22
lang: en
authors: [claude-opus-5-5]
approvers: [operator 2026-10-22]
story: [US-050]
supersedes: []
amends: [ADR-0026]
related: [ADR-0027, ADR-0017]
evidence:
  - path:docs/proposals/20261022-codebase-modularization.md
  - commit:b0acee2
  - "operator:2026-10-22 approved deleting the unused manual tools listed in PRP-20261022-codebase-modularization F4, including opencode_native_run.py"
summary: "ADR-0026.D3 keeps its runner order, but the manual batch helper scripts/opencode_native_run.py is deleted; opencode runs only through article_run.py --runner opencode and run_backlog_opencode.py."
summary_vi: "Giữ thứ hạng runner của ADR-0026.D3 nhưng bỏ script chạy lô thủ công opencode_native_run.py; opencode chỉ chạy qua article_run.py --runner opencode và run_backlog_opencode.py."
---

# ADR-0028 — Retire the manual opencode batch script from the runner order

## Context

- ADR-0026.D3 ranks the LLM runners agy, `opencode run`, then OpenRouter, and names `scripts/opencode_native_run.py` as the way to run manual opencode batches.
- The reachability scan of PRP-20261022-codebase-modularization found that no live entry point called `opencode_native_run.py`; it bypassed `article_run.py` and therefore the manual-wave gate, the ledger and the `--finish` DoD gate.
- The operator approved deleting it on 2026-10-22 with the other unused manual tools (commit `b0acee2`). The body of ADR-0026 is frozen (K-R8), so the change needs its own record.

## Decision

- **ADR-0028.D1:** The runner order of ADR-0026.D3 stays: agy, `opencode run`, OpenRouter; Claude is never a replacement runtime.
- **ADR-0028.D2:** `opencode` runs only through `scripts/article_run.py --runner opencode` (one wave) and `scripts/run_backlog_opencode.py` (a sequence of waves). Both go through the manual-wave gate, the ledger and `--finish`.
- **ADR-0028.D3:** The reference to `scripts/opencode_native_run.py` in ADR-0026.D3 is void. The old file is recoverable with `git show ec4e7fe:project/scripts/opencode_native_run.py`.

## Alternatives

| Option | Why rejected |
|---|---|
| Restore the script | It skipped the wave gate and the ledger, which ADR-0017 and ADR-0026 require for every provider. |
| Leave ADR-0026 pointing to a deleted file | Agents would follow a dead instruction. |

## Consequences

- One path per runner: every opencode batch is traced, ledgered and gated like agy batches.
- Ad hoc single-batch experiments with opencode use a small `--limit` wave instead of a separate script.

## Rollback

- Restore the file from commit `ec4e7fe` and set this ADR to `superseded`. Only the operator may order the rollback.

## Follow-up

- [x] ADR-0026 frontmatter lists ADR-0028 under `amended_by` or the index shows the amendment.
