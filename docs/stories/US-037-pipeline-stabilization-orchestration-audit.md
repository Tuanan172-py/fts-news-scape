---
id: US-037
type: story
title: Pipeline stabilization after the orchestration audit
status: implemented
lane: normal
created: 2026-10-05
updated: 2026-10-06
lang: en
authors: [An Pham Thanh, claude-opus-5-5]
adr: [ADR-0019, ADR-0018, ADR-0012]
plan: []
evidence:
  - commit:737d8ce
  - commit:aa49b5d
  - commit:0340f64
  - commit:b7f1a37
  - commit:1ae81be
  - commit:ac9f22f
  - path:docs/proposals/20261005-audit-dieu-phoi-agent.md
  - path:project/src/ops/manual.py
  - path:project/src/ops/lanes.py
  - path:project/scripts/article_pack.py
  - path:project/src/agent/silver_source.py
  - test:project/tests/test_ops_manual.py
  - test:project/tests/test_article_pack_thin.py
  - test:project/tests/test_wave_thin_demote.py
  - test:project/tests/test_ledger_openrouter.py
  - metric:audit findings F1 to F10 over waves W10051042, W10051050 and W10051122, 2026-10-05
  - operator:keep manual runs, lock provider per wave, copy raw_html instead of re-crawling, 2026-10-05
verify: "python -m pytest project/tests/test_ops_manual.py project/tests/test_article_pack_thin.py project/tests/test_wave_thin_demote.py -q"
reconstructed: 2026-10-06
summary: Self-running waves cannot drift after the 2026-10-05 audit; provider is locked per wave, repair rounds are capped, failed waves cool down, manual runs are registered, thin articles leave packets, and data leaves git.
---

# US-037 — Pipeline stabilization after the orchestration audit

## Contract

After this story, no wave runs off the books. The provider stays fixed for a wave, repair rounds and per-article attempts have a real ceiling, and a failed wave triggers a cool-down. Manual runs register themselves, and operational data no longer lives in git.

## Acceptance Criteria

- [x] R-01: agy stores its raw response when a batch returns no records (`ops_logs/waves/<wave>/raw/`).
- [x] R-02: provider is locked per wave; manual runs use `--mode backlog|bench|adhoc` and register `ops_waves`, spans and article holds (`src/ops/manual.py`); OpenRouter gets spans.
- [x] R-03: every repair round counts an attempt per article; `/retry` is refused after `max_repair_rounds` rounds.
- [x] R-04: a failed wave starts a 30-minute cool-down (`wave.cooldown_minutes`).
- [x] R-05: a Git Bash path-shaped command is restored to its slash form or rejected.
- [x] Run lanes auto, backlog and bench allow one wave each (`src/ops/lanes.py`); failed waves W10021650, W10051042 and W10051050 are released with `/cancel`.
- [x] ADR-0019: thin articles (fewer than two paragraphs of `MIN_CITATION_CHARS`) are excluded from packets and counted separately on the radar.
- [x] Data plane decoupled: generated data, packets, outputs, reports and binary documents are untracked and ignored.
- [ ] R-06: the daemon runs `capture_reconcile.py` on its own cycle. Not done; it overlapped the US-036 capture session.
- [ ] R-07: delivered by US-036 (raw_html merge and `RawStore` anchoring), not by this story.
- [ ] R-08 remainder: documentation sync and the stability check of plan section 5 before L1 is granted again.

## Design Notes

- Source: orchestration audit `docs/proposals/20261005-audit-dieu-phoi-agent.md` with findings F1 to F10. Daemon and `article-processor` complied; violations came from manual sessions and three mechanism gaps.
- The R-01 to R-08 plan sits in a tool-private plan file (`lovely-herding-moler.md`); per K-R10 it is not cited as a plan here.
- Operator decisions of 2026-10-05: keep manual runs for backlog and benchmarks, lock the provider per wave with `/provider` as the only override, copy raw_html rather than re-crawl.
- ADR-0019 body records that it was first drafted as a second ADR 0018; that mismatch is historical and stays in the body.
- Silver-first packing and stale-packet refresh (ADR-0018) shipped in commits labelled US-036; they are Article Lane packing work and belong here.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `verify` command in frontmatter plus the ops suite | ops suite and `test_ops_manual.py` green, 2026-10-05 |
| Integration | full suite from `project/` | 5 failures outside scope (`test_inherit` 1, `test_periodic_reports` 4), 2026-10-05 |
| Platform | daemon restarted on the new code | done, 2026-10-05; L1 stability conditions not yet met |

## Evidence

- Commit 737d8ce: data plane decoupling, ADR-0019, `manual.py`, `lanes.py`, cool-down, ledger for OpenRouter, thin-article tests. It also carried US-036 write-point anchoring.
- Commit aa49b5d: session handoff for the data plane decoupling.
- Commit 0340f64 (commit labelled US-036): `silver_source.py` and the thin filter in `article_pack.py`.
- Commit b7f1a37 (commit labelled US-036): finds a Silver package across days within a domain.
- Commit 1ae81be (commit labelled US-036): defensive column access in `row_paragraphs`.
- Commit ac9f22f (commit labelled US-036): stale packet refresh decided by the count of eligible paragraphs.
- Commit b14054f mentions US-037 only in its body (a fixture untracked here comes back); its subject is US-038 and it is not part of this story.
