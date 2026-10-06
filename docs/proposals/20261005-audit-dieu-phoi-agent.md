---
id: PRP-20261005-audit-dieu-phoi-agent
type: proposal
title: Orchestration audit of agents acting outside the workflow
status: decided
lane: normal
created: 2026-10-05
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0012, ADR-0013, ADR-0014, ADR-0017]
story: [US-037]
plan: []
evidence:
  - wave:W10051042
  - wave:W10051050
  - wave:W10051122
  - path:docs/OPEN-ITEMS.md
  - metric:0 Zero-Tool violations across all traces since 2026-10-02
  - metric:W10051042 ran 3 batches on agy and 5 on openrouter under a "failover never" mandate
  - commit:0340f64
original: "commit:0340f64"
reconstructed: 2026-10-06
summary: Asks whether agents ran outside the workflow or against instructions; finds daemon and article-processor compliant, with violations from manual waves and three mechanism gaps, fixed in order under US-037.
summary_vi: Audit cho thấy daemon và article-processor tuân thủ; vi phạm do đợt chạy tay và ba lỗ hổng cơ chế, xử lý theo thứ tự trong US-037.
---

# PRP-20261005-audit-dieu-phoi-agent — Orchestration audit of agents acting outside the workflow

## Question

- Did any agent run outside the workflow or against its instructions, and what MUST be fixed first?
- Scope: `ops.db` (waves, events, spans) from 2026-10-02; packet and output files of waves W10051042, W10051050 and W10051122; radar; harness audit.
- Method: read-only queries; no data was modified.

## Findings

- The daemon and `article-processor` complied wherever compliance was checkable. All traces show 0 tool calls against Zero-Tool. Every daemon-opened wave has complete spans and article reservations.
- The violations came from humans and sessions outside the daemon intervening in waves, plus three mechanism gaps.

| # | Severity | Finding | Evidence | Action |
|---|---|---|---|---|
| F1 | High | W10051122 ran outside the daemon: 500 articles, 27 batches plus repairs, no `ops_waves` row, 0 spans, 0 reserved articles | `ops_spans` and `ops_wave_articles` both 0 for this wave | Every runner MUST write `ops_waves` and spans (S-18); lock manual waves while the daemon is alive (ADR-0012) |
| F2 | High | Daemon opened W10051042 with provider `agy`, but 5 batches ran on `openrouter` (`stealth/space-bunny-alpha`) after `/retry` | Output meta: agy 3 batches, openrouter 5; mandate says `failover never` | Block provider change mid-wave: `retry_wave` keeps the wave provider, or logs a `provider.override` event |
| F3 | High | Repair limits exceeded. Config `max_repair_rounds: 2`, `max_attempts_per_article: 2`. In W10051042, 47 articles were packed 4 times and 3 articles 8 times; W10051122 had one article packed 9 times | Counts in `*.map.json` | `retry` and manual repair MUST count toward the article's attempts and MUST NOT reset the counter |
| F4 | Medium | No cooldown after a failed wave: W10051050 opened 8 minutes after W10051042 failed for the same cause, spent tokens and failed again. L1 dropped to L0 only after the second failure | Events 10:48 to 10:55 | The first failed wave SHOULD set a cooldown (proposed 30 minutes) before the sensor opens a new wave |
| F5 | Medium | Runner system fault, not a model fault: a 50-article batch returned 0 articles ("Bóc tách JSON thất bại") at 105 to 126 seconds, repeated every repair round. Content coverage 58% against 100% identification | Agent span `fail`, `verify_wave` | Diagnose the empty agy response at batch 50; try batch 25 while ADR-0017 D6 and D7 are pending |
| F6 | Medium | `/retry` typed in Git Bash became `C:/Program Files/Git/retry` and was still logged as `human.command` | Two events at 10:53 | The command parser MUST reject strings not starting with `/` and report a clear error |
| F7 | Medium | Capture layer red under ADR-0013: baodautu missing 66%, cafef 61%, tinnhanhchungkhoan 61%; 976 URLs awaiting backfill; 122 Bronze stuck before Silver; 1,241 articles missing Bronze | `pipeline_radar.py status`; grep of `src/ops` | Wire `capture_reconcile.py run` into the daemon cycle; the daemon `reconcile()` only restores workflows |
| F8 | Low | Model differs from documents: the agent ran `gemini-3.8-flash-low`, while AGENTS.md §6C said every model is `deepseek-flash`; the registry said only `flash` | ADR-0017 already noted ADR-0009 D6 is no longer true | Update AGENTS.md §6C and `registry.yaml` once ADR-0017 is in force |
| F9 | Low | Mandate at L0 after the automatic drop; `/level L1` at 14:02 lacked `confirm`, so the daemon did not open waves although the oldest article had waited 291 minutes | `human.command` 14:02, radar | Type `/level L1 confirm` to resume; fix F2 and F5 first |
| F10 | Low | Three `FAILED` waves from 2026-10-02 and 2026-10-05 still held their articles | `ops_waves` | `/cancel` W10021650, W10051042 and W10051050 after deciding to keep or drop them |

### What complied

- 0 Zero-Tool violations and 0 denied tool turns across all traces.
- Every daemon-opened wave passed through the `--finish` gate; waves that failed the gate were blocked from DB ingest by design.
- The L1 to L0 drop after two failed waves worked and raised an urgent alert.
- Privilege escalation needs double confirmation; both `/level L1` commands passed confirmation before any wave opened.

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| A. Fix in the proposed order: F2 and F3, then F4 and F5, then F1 and F7, then F6, F8, F9, F10 | Stops token waste and provider drift first | Capture gaps (F7) stay red a little longer |
| B. Fix capture (F7) first | Restores ADR-0013 completeness sooner | Failed waves keep burning tokens and mixing providers meanwhile |
| C. Only document the findings | No engineering cost | Manual waves stay invisible and repair limits stay unenforced |

## Recommendation

Option A, in this order:

1. F2 and F3: block provider change and repair overrun; fix `retry_wave` and the per-article counter.
2. F4 (cooldown) and F5 (empty batch).
3. F1 through S-18; F7 by wiring `capture_reconcile` into the daemon.
4. F6, F8, F9, F10.

## Outcome

- Decided: the findings were taken into story US-037 (session 2026-10-05), which added spans for the OpenRouter runner and traced manual waves (per ADR-0014).
- Remaining US-037 items were recorded in `docs/OPEN-ITEMS.md` section OPS-3 on 2026-10-05: backfill throughput, releasing waves W10021650, W10051042 and W10051050, a raw-response run of a 50-article agy batch, an official `--runner opencode`, and L1 re-grant criteria.
- Reconstructed 2026-10-06: the link to US-037 and the OPS-3 follow-up come from `docs/OPEN-ITEMS.md` and ADR-0014, not from this audit's original text.
