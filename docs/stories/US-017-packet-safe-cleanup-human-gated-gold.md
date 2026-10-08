---
id: US-017
type: story
title: Packet-safe cleanup and human-gated Gold activation
status: retired
lane: high-risk
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0008, ADR-0010]
plan: []
evidence: [commit:0f1a65c, path:project/scripts/maintenance/clean_completed_packets.py, path:project/scripts/auto_pilot.py, test:project/tests/test_destructive_automation_guards.py, metric:428 tests passed]
verify: "cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q"
reconstructed: 2026-10-06
summary: Cleanup could no longer delete unprocessed packets, Gold spent no tokens without explicit human approval, and failures exited non-zero; retired when ADR-0010 ended the Gold lane.
---

# US-017 — Packet-safe cleanup and human-gated Gold activation

## Contract

- Automation MUST NOT be able to delete an unprocessed packet, by construction (reconstructed from the harness.db row).
- Gold MUST NOT consume tokens until a human grants explicit permission.
- A failure MUST exit loudly and MUST NOT print a false "100% complete".
- Retired: ADR-0010 ended the Gold lane and ADR-0008 is superseded, so the Gold activation gate no longer runs.

## Acceptance Criteria

- [x] `CleanPackets` deletes only packets with evidence of completion; the default keeps packets.
- [x] `-Mode full` and the dead hierarchy branch are removed.
- [x] Batch names are unique per run.
- [x] AutoPilot asks for permission before calling `agy`, and `--dangerously-skip-permissions` leaves the default path.
- [x] `run_cmd` returns non-zero on error; batch and token caps exist.

## Design Notes

- Decision in ADR-0008; phase 02 of plan `20260917-1420-pipeline-integrity-remediation`.
- `clean_completed_packets.py` deletes only packets with `dod_pass=1`, defaults to dry-run and skips `archive/` (reconstructed from trace 52).
- Batch codes carry a run timestamp plus four random characters, because two runs in the same second collided.
- Trace 52 notes that the permission prompt sits after export, so a refusal still leaves a new packet.
- The token caps of ADR-0008 conflict with the later rule that token counts are a record, not a gate (US-026).

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/ -q` | 428 passed, 10 new |
| Integration | dry-run of `clean_completed_packets` on production packets | 0 deleted, 170 kept |
| Platform | `-Mode full` call and the permission gate without TTY | rejected by ValidateSet; gate exits 1 without `--yes` |

## Evidence

- Commit 0f1a65c (2026-09-17), "complete integrity remediation across phases 01-04 (US-011..US-019)".
- harness.db story row US-017 and trace 52, outcome `completed`.
- ADR-0010 retires the Gold lane; ADR-0008 status is `superseded`.
