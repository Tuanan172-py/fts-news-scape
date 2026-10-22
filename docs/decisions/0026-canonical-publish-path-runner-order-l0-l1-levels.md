---
id: ADR-0026
type: adr
title: Canonical publish path, runner order, L0/L1 levels, user manifest SSOT, users/output tree
status: accepted
lane: high-risk
created: 2026-10-21
updated: 2026-10-21
lang: en
authors: [operator, claude]
approvers: [operator 2026-10-21]
story: [US-045]
supersedes: []
amends: [ADR-0012]
amended_by: [ADR-0028]
related: [ADR-0010, ADR-0017, ADR-0020, ADR-0023, ADR-0025]
evidence:
  - path:project/src/ops/runtime/order.py
  - path:project/src/export/publisher.py
  - path:project/src/core/user_manifest.py
  - path:project/scripts/maintenance/migrate_users_output.py
  - test:project/tests/ops/test_ops_core.py
  - test:project/tests/core/test_user_manifest.py
  - test:project/tests/core/test_migrate_users_output.py
summary: "Fixes six ambiguities found when mapping the architecture. One production publish path, ranked LLM runners without Claude, autonomy levels L0 and L1 only, one user manifest, one users/output tree for local and SharePoint, and harness tracking that never gates."
summary_vi: "Chốt sáu điểm lệch: một đường xuất bản chuẩn, thứ hạng runner (không có Claude), chỉ còn L0/L1, một manifest người dùng, một cây users/output, harness chỉ theo dõi không chặn."
---

# ADR-0026 — Canonical publish path, runner order, L0/L1 levels, user manifest SSOT, users/output tree

## Context

- The architecture map of 2026-10-21 found that the documents and the code disagree on six points.
- Two scripts could both write Lakehouse Parquet: `scripts/publish.py` and `scripts/lakehouse_cli.py`.
- `order.py` silently read legacy levels L2 and L3 as L1, which contradicts the amendment in ADR-0012 D5.
- Two manifests held user switches: `project/config/entities/manifest.yaml` and `users/subscriptions/manifest.yaml`. An operator could edit the wrong one and the pipeline would not change.
- Excel output lived in `<root>/users_output` locally but in `users/output` on SharePoint, so scripts and tests lost their way between the two trees.
- `harness_cli.py session close` blocked on a failing verify command, yet set `implemented` and `unit_proof=1` when verify was skipped. It acted as a gate and as a weak proof at once.
- Claude was listed as an interchangeable runtime although no code path exists for it (ADR-0017).
- ADR-0023 superseded ADR-0020; `publisher.py` still cites ADR-0020 in its docstring.

## Decision

1. **D1 Canonical publish path.** The only production publish path MUST be `scripts/publish.py` calling `src.export.publisher.publish_day()`. `scripts/lakehouse_cli.py` MUST be used only for `verify` (audit) and as the external dropzone gateway; it MUST NOT publish for the ecosystem.
2. **D2 Harness tracks, it does not gate.** `harness_cli.py session close` MUST record verify outcome, push outcome and friction in the trace and MUST continue after a failed verify. A story MUST become `implemented` with `unit_proof=1` only when its verify command actually passed. `--strict` MAY be passed to abort on a failed verify. Evidence prefix `trace:` is allowed.
3. **D3 Runner order.** LLM runners for the Article Lane rank: 1 `agy` (primary), 2 `opencode run` (`src/agent/opencode_runner.py`, `--runner opencode`; manual batches via `scripts/opencode_native_run.py`), 3 OpenRouter API. Claude MUST NOT be a replacement runtime. The DSH `agent_article` path remains the interactive conductor.
4. **D4 Levels.** The system MUST have exactly two autonomy levels: L0 (stop, lock, measure only) and L1 (mandate with a per-wave article cap, `max_limit`). `order.py` MUST NOT map L2 or L3 to L1; an unknown level in the order file reads as L0. The command `/level L2` or `/level L3` MUST be refused with the message "Hệ thống đã chuẩn hóa L0/L1 theo ADR-0012 (Amended). Vui lòng dùng /level L1 <số bài>". `/level L1 <n>` sets the cap, 1 to 500.
5. **D5 User manifest SSOT.** `<DATA_ROOT>/subscriptions/manifest.yaml` (seed copy `users/subscriptions/manifest.yaml`) MUST be the only place that enables or disables users. Absent users default to ON. `project/config/entities/manifest.yaml` is retired and deleted. It held no ticker mapping, so no `ticker_directory.yaml` is created. Compiled watchlists stay in `project/config/entities/users/*.yaml`.
6. **D6 One output tree.** Excel delivery MUST live at `<DATA_ROOT>/users/output/<user>/<YYYY-MM-DD>.xlsx`, identical to the SharePoint tree. `paths.users_output_dir()` returns `<DATA_ROOT>/users/output`. `scripts/maintenance/migrate_users_output.py` moves the old `users_output/` tree.
7. **D7 Lineage.** ADR-0023 supersedes ADR-0020. ADR-0020 stays superseded and MUST NOT be cited as current.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep `lakehouse_cli` as a second publisher | Two writers of one Parquet partition risk divergent manifests; the 1-year backfill (US-038) already ran through `publish_day` only. |
| Keep silent L2/L3 mapping with a warning | It hides an operator typo as a full mandate; refusing is safer and costs one retyped command. |
| Keep both manifests and sync them | Two files need a sync rule and a conflict rule; one file needs neither. |
| Keep `users_output` locally, map on publish | The mapping is the source of the `FileNotFoundError` risk this ADR removes. |
| Keep `session close` as a hard gate | A failed verify then blocks the trace itself, which is the record the harness exists to keep; multi-agent work needs the record more than the stop. |

## Consequences

- One publish path, one manifest and one output tree remove three classes of wrong-file errors.
- The old Excel tree must be migrated before the next delivery run, otherwise the idempotency checkpoint will not see earlier files and may re-deliver. The migration script runs a dry-run by default.
- Operators who typed `/level L2` now get a refusal and must retype `/level L1 <n>`.
- A story can stay `in_progress` after `session close` when verify fails. This is intended: the trace says so and the next session sees it.
- The golden set for provider conformance is still unlabelled, so the runner order is an operating preference, not a scored ranking.

## Rollback

- Revert the commit that carries this ADR to restore the previous code and the retired manifest.
- Run the migration script in reverse by moving `users/output` back to `users_output`; the dry-run output lists every file.
- The previous live manifest is kept as `subscriptions/manifest.yaml.bak-us045` under the data root. The operator performs the rollback.

## Follow-up

- [ ] Run `python scripts/maintenance/migrate_users_output.py --apply` on the operating machine while the daemon is stopped.
- [x] Update the `publisher.py` docstring from ADR-0020 to ADR-0023.
- [ ] Label the golden set so ADR-0017 D7 can score `agy`, `opencode` and OpenRouter.
