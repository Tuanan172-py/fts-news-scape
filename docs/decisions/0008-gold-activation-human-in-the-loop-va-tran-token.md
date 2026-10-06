---
id: ADR-0008
type: adr
title: Human-in-the-loop Gold activation and token cap
status: superseded
lane: high-risk
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [An Pham Thanh (commit author)]
approvers: [operator 2026-09-17, operator 2026-09-18 (amendment)]
story: [US-017]
evidence:
  - commit:0f1a65c
  - commit:3f9d59e
  - commit:eeccd9f
  - commit:46f617f
  - path:plans/20260917-1420-pipeline-integrity-remediation/phase-02-destructive-automation.md
  - path:plans/20260918-1651-article-lane-unified/plan.md
  - path:project/scripts/auto_pilot.py
  - test:project/tests/test_destructive_automation_guards.py
  - metric:pre-run token estimate deviated 21 to 90 times from measured cost, article-lane plan 2026-09-18
  - metric:about 0.31 USD per 1,000 articles per day at off-peak pricing, article-lane plan 2026-09-18
  - operator:"bắt buộc human phải ở trong loop và đưa ra permission" (2026-09-17)
  - operator:"bỏ hẳn cổng ADR 0008 (người xác nhận), tôi sẽ quản lý theo batch hoặc wave" (2026-09-18)
original: "commit:3f9d59e"
reconstructed: 2026-10-06
summary: Required explicit operator confirmation and a per-run token cap before any LLM runner spent tokens, and made failures loud; the gate and cap were voided on 2026-09-18 and by ADR-0010; only fail-loud survives.
summary_vi: Bắt buộc người vận hành xác nhận và có trần token trước khi tiêu token, thất bại phải ồn ào; cổng và trần đã bị gỡ, chỉ còn nguyên tắc thất bại phải ồn ào.
---

# ADR-0008 — Human-in-the-loop Gold activation and token cap

## Context

- `auto_pilot.py` lines 80 to 88 called the external CLI `agy` with the flag `--dangerously-skip-permissions`.
- Four problems stacked up.
- P1, no human in the loop. The LLM agent was triggered automatically and spent the user's account tokens without confirmation. The flag also disabled the tool's own permission prompts.
- P2, no cost cap. No limit on batches, no token estimate before running, no stop on exceeding a budget.
- P3, silent failure reported as success. `run_cmd` (lines 29 to 31) only printed errors and continued. A bare `except Exception` (line 89) swallowed `FileNotFoundError` when `agy` was missing.
- Line 100 printed "100% complete" unconditionally. Combined with batch-name collisions (`batch_NN` restarted at 01 every run), the system could re-ingest old data and report success.
- P4, not reproducible. `agy.exe` lived in the user's `AppData\Local\agy\bin\` folder, outside the repository, with no pinned version and no entry in `requirements.txt`.

```
agy -p <prompt> --dangerously-skip-permissions --effort low
```

The operator directive on 2026-09-17 was: "bắt buộc human phải ở trong loop và đưa ra permission".

## Decision

- D1. Gold MUST NOT be activated without explicit operator confirmation. Every path that calls `agy`, or any later LLM runner, MUST stop and ask first. It MUST show the number of batches and articles, the token or cost estimate, and the `--effort` mode.
- D1a. Running without confirmation is allowed only through an explicit flag such as `--yes`, typed by the operator. The default is always to ask.
- D2. The flag `--dangerously-skip-permissions` is removed from the default path. It MAY be used only when the operator turns it on, with clear logging. By default `agy` keeps its own permission prompts.
- D3. Token cap per run. A cap parameter (maximum batches and/or estimated token budget) is added. Exceeding it MUST stop cleanly and report the work done, following the `--budget-seconds` pattern already applied to `backfill_deferred`.
- D4. Failures MUST be loud. `run_cmd` returns non-zero when a child command fails. The bare `except` is removed. The output file MUST be verified to exist before a batch counts as done. The summary line reflects the real number of successful batches.
- D5. `run_daily.ps1 -Mode full` is removed. `full` did not run Gold (`[ValidateSet('api')]` blocked the `hierarchy` branch and the `default` branch only printed text) yet still deleted packets. Only `emit` and `ingest` remain; the agent call is the middle step, triggered by the operator under D1.
- D6. `agy` becomes a declared dependency: pinned version, documented in the install guide, and checked for existence before running instead of letting `FileNotFoundError` be swallowed.

### Amendment history

**2026-09-18, operator directive** "bỏ hẳn cổng ADR 0008 (người xác nhận), tôi sẽ quản lý theo batch hoặc wave". Anchor: `plans/20260918-1651-article-lane-unified/plan.md` §2 Q4 and §9.2. Content preserved:

- Why the original no longer fit. The ADR was written when tokens were spent through an external tool with all permission prompts skipped, no estimate before, no measurement after, and unconditional success reports. The human gate was then the only protection.
- All three conditions changed. First, every token spend now starts with an explicit operator command (`article_run.py --wave N`); no path starts by itself, so running the command is the decision.
- Second, there is an estimate before and a measurement after. `estimate_wave.py` prints the cost before running and `token_ledger.py` records real runtime figures afterwards with a deviation check. The old gate showed only an estimate, later shown to deviate 21 to 90 times from reality.
- Third, cost is measured and small: about 0.31 USD for 1,000 articles a day at off-peak pricing. The real constraint is the account token quota, tracked by the ledger rather than a question before each run.
- D1 and D3 are void. No human confirmation gate may be rebuilt under any name. Two automatic technical stops replace them. They protect quality, not the wallet, so they ask nobody.

| Stop | Triggers when | Behaviour |
|---|---|---|
| Context ceiling | estimated batch exceeds 25% of the window | `article_pack.py` splits the batch |
| Failure threshold | broken records exceed 10% in a wave | `article_run.py` stops the wave before loading the database |

- D4 is kept in full. It is the most valuable clause of this ADR and unrelated to the confirmation gate. It is implemented in code: a non-zero child exit stops the whole wave and prints the reason.
- D2, D5 and D6 no longer have an object, because the external tool was replaced by a runtime under project control.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep everything and only fix the batch-name collision | Does not address tokens spent without approval, which was the operator's stated concern. |
| Replace `agy` with an SDK inside the repository | Large architecture change that needs its own ADR and a provider choice; it must not block this remediation. |
| Full automation with a token cap and no confirmation | The operator explicitly required a human in the loop; a token cap alone does not replace consent. |

## Consequences

Gains at acceptance:

- No accidental token burn; failures surface instead of hiding behind "100% complete"; Gold becomes reproducible on another machine.

Costs accepted at acceptance:

- Gold no longer runs fully unattended. This was a deliberate trade: the operator preferred cost control over full automation.
- The Gold queue grows while nobody triggers it; the radar MUST show it clearly so it is not forgotten.

Acceptance tiers defined by the original ADR:

| Tier | Condition |
|---|---|
| Unit | Missing `agy` gives a clear error and non-zero exit, not swallowed |
| Unit | Two calls of `split_tasks_into_batches` produce different batch names |
| Unit | Exceeding the batch or token cap stops cleanly and reports work done |
| Integration | A simulated `agy` failure does not print "100% complete" |
| Platform | Real run shows a permission prompt before tokens are spent |

### Current status (2026-10-06)

- Status `superseded`. ADR-0010 declares that it supersedes this ADR.
- D1 dead since the 2026-09-18 amendment. ADR-0014 states the human approval gate MUST NOT be rebuilt.
- D3 dead. ADR-0010.D5 makes tokens a recorded figure, never a gate, at article, batch or wave level.
- The amendment's context-ceiling stop was removed on 2026-09-21 (commit eeccd9f): it never triggered, and `--batch` became the only batch splitter.
- The amendment's 10% failure threshold survives inside `--finish`; `article_run.py` sets `MIN_COVERAGE = 0.90` and ties it to that threshold.
- D4 lives on as `--finish` fail-loud. Commit 46f617f made `l1_ingest.py` and `agent_ingest.py` exit non-zero when DoD rejects a record, citing this clause.
- D2, D5 and D6 dead (no object). The `agy` runner is governed by ADR-0011.

## Rollback

- The original ADR names no rollback procedure. Restoring the gate means reverting the 2026-09-18 amendment of commit 3f9d59e and rebuilding the confirmation path in `auto_pilot.py` (reconstructed from the commit history).
- Any such rollback conflicts with ADR-0010 and ADR-0014, so it needs a new high-risk ADR approved by the operator.

## Follow-up

- [x] Fail-loud exit codes for ingest commands (commit 46f617f).
- [x] Context-ceiling auto split removed (commit eeccd9f).
- No open items. Later direction belongs to ADR-0010 and ADR-0014.
