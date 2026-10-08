---
id: PRP-20260923-agy-automation-council
type: proposal
title: Automate Article Lane with the Antigravity CLI (agy)
status: decided
lane: high-risk
created: 2026-09-23
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0010, ADR-0011]
story: [US-025, US-026, US-027, US-028]
plan: []
evidence:
  - path:docs/proposals/20260923-agy-automation-council/dossier_round1.md
  - path:docs/proposals/20260923-agy-automation-council/spike1-RESULTS.md
  - path:docs/proposals/20260923-agy-automation-council/spike2-RESULTS.md
  - metric:custom agent in worker profile cut input 24.9k to 13.6k tokens per call (-45%), spike 2026-09-23
  - metric:Windows argv ceiling 32,767 characters; 32,000 passes, 32,800 fails with WinError 206
  - metric:agy updated itself from 1.2.7 to 1.2.9 during the two-day review
  - commit:8ec12f8
original: "commit:8ec12f8"
reconstructed: 2026-10-06
summary: Asks how to run Article Lane unattended with agy; recommends Python as conductor and agy as a zero-tool single-turn function in an isolated worker profile, adopted by ADR-0011.
summary_vi: Hội đồng đề xuất Python điều phối, agy là hàm nhận thức một lượt không tool trong hồ sơ worker cô lập; đã thành ADR-0011.
---

# PRP-20260923-agy-automation-council — Automate Article Lane with the Antigravity CLI (agy)

## Question

- How should Article Lane run unattended with `agy`, beside DSH, for the single cognitive stage `article_analyze`?
- The proposal was classified Tier 3 high-risk (AGENTS.md §0): it touches the automation substrate and adds a provider. Precedent: ADR-0009.
- Working papers sit in [20260923-agy-automation-council/](20260923-agy-automation-council/): one dossier, three position papers, three rebuttals and two spike result files.

### Council process

| Round | Members | Output |
|---|---|---|
| 1, research | A agy facts (web plus 11 test commands), B repo pipeline and governance, C Windows trigger and subprocess, D agy native features | `dossier_round1.md` |
| 2, positions and spikes | D1 pure function (8 agy commands), D2 agy-native MCP and hooks (8 commands), D3 operations and governance red team | `position_1..3.md`, `spike1/2-RESULTS.md` |
| 3, cross rebuttal and deciding spike | D2 tested a custom agent in the worker profile (5 commands); D1 and D3 rebutted | `rebuttal_1..3.md` |

## Findings

Labels: [V] verified on the machine, [S] sourced, [I] inferred.

- F1. `agy -p` ignores stdin in text mode [V]. `--input-format stream-json` with NDJSON `{"event":"user","message":{"content":"..."}}` works and keeps Vietnamese UTF-8 intact [V]. Payload MUST go through stdin stream-json.
- F2. The Windows argv ceiling is 32,767 characters: 32,000 passes, 32,800 fails with WinError 206. `cmd.exe` caps at 8,191 [V]. Articles MUST NOT be passed in `-p`.
- F3. False success exists. A denied tool returns exit 0, `SUCCESS`, `response:""` plus `denied_actions`. A `--print-timeout` expiry returns exit 0 with usage 0, reported only on stderr [V]. API errors return exit 3 plus `AGY_ERROR:{retryable}` [S changelog]. The classifier MUST NOT trust exit codes.
- F4. Default agy carries about 11.7k system prompt tokens and 57 tools per call. `cache_read` is 0 across processes, even for near-identical prefixes [V]. Cache MUST NOT count in any budget.
- F5. Workspace agents (`.agents/agents/*.md`) did not load; agy silently fell back to the default agent with exit 0, while the `init` event still named the custom agent [V]. Agent loading MUST be checked in `cli.log`.
  - Probable cause [I]: the workspace path was not trusted (log `loaded 0 named hooks from 0 hooks.json`). F7 gave a verified alternative, so this was not pursued.
- F6. Pointing `USERPROFILE`, `HOME` and `ANTIGRAVITY_APP_DATA_DIR` at a separate worker profile makes agy load only that profile's allowlist, hooks and agents; login still uses the keyring [V]. This isolates from the global allowlist entry `command(regex:.*\.py$)` and replaces `--dangerously-skip-permissions`.
- F7. A global custom agent in the worker profile loads (`agent=true` in the log) with `excludeDefaultComponents: true`, `tools: []` and body equal to CORE [V].
  - Input fell from 24.9k to 13.6k tokens (-45%), in one turn.
  - 5 of 5 records came back in order, with 0 wrong group codes against a 15% baseline error rate.
  - The agent ignored a `view_file` lure. This is the reference configuration.
- F8. agy implements `--json-schema` through a hidden `finish` tool that conflicts with `tools: []` [V].
  - It looped 4 turns at 2.4x to 3.6x tokens without `structured_output`.
  - Top-level arrays and `prefixItems` were rejected (HTTP 400, exit 3).
  - Decision: no `--json-schema`; Python parses with `salvage_records`, then jsonschema and domain checks.
- F9. Hooks (`PreToolUse`, `PostToolUse`, `Stop`) run under `-p`. A crashing hook blocks the tool (fail-safe). `Stop` does not run when a permission denial ends the call [V]. A deny-all hook is a secondary defence only.
- F10. `agentapi` and the sidecar need the Antigravity app running (`ANTIGRAVITY_LS_ADDRESS is not set`, exit 0) and a manual dashboard toggle. `remote-control` is a human UI [V]. Both are excluded as triggers.
- F11. Three parallel `agy -p` processes ran fine [V]. Quota shares the "Work Done" pool with IDE and interactive use, refreshed every 5 hours with a weekly cap [S]. Pool size 2 and a quota guard were proposed.
- F12. Repo preconditions were broken [V]:
  - The real DB is `C:\data\news-scape\monocle.db` via env `MONOCLE_DB_PATH`, while `settings.yaml:3` pointed at the old OneDrive copy, a split-brain risk for scheduled tasks without the env.
  - `article_run.py:435-450` ran `--finish` ingest with `check=False`, swallowing errors against ADR-0008 §2.4.
  - `news_cron` collided with `morninger` (OPEN-ITEMS A0-5). These were assigned to US-025.

### Batch size model

Fixed cost after the custom agent is about 8k tokens including CORE. Each article costs about 1.1k input and 0.3k output [V on a 5-article sample, I at scale].

| N | Input per call | Output per call | Fixed share | Tokens per 1,000 articles |
|---|---|---|---|---|
| 25 | ~36k | ~7.5k | ~22% | ~1.74M |
| 50 | ~63k | ~15k | ~13% | ~1.56M |
| 100 | ~118k | ~30k | ~7% | ~1.48M |

- Batch 100 saves only about 5% over 50 but doubles retry loss and truncation risk. D2 proposed 25 to 30; the council chose 50, with spike B to decide.

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| A. Python conductor, agy as zero-tool single-turn function in an isolated worker profile, stdin stream-json, Python validation | 45% less input (F7), no tools to inject into, deterministic control | Needs profile rebuild per tick, version pin and a failure classifier |
| B. Earlier draft: stdin `--input-format text`, `--dangerously-skip-permissions`, array schema with `prefixItems`, batch 25 | Simple | Fails on F1 and F8; breaks ADR-0008 §2.2 |
| C. Fully autonomous agy conductor that decides which scripts to run | No Python orchestration code | Violates Rule 01 §1 and Rule 07; bugs #1044, #902, #1077; prompt injection with 57 tools plus a `.py` allowlist |
| D. MCP pull worker (claim and submit) | Runs without skip-permissions [V] | 7 turns and 96.5k tokens for 3 articles (about 2.5x to 30x one-shot); D2 withdrew it |
| E. Long-lived multi-turn stream-json worker | Cache within one conversation | Context growth and cross-batch leakage outweigh cache gains |
| F. Sidecar, `agentapi` or remote-control | Native integration | Needs the desktop app running (F10) |
| G. Watchdog on OneDrive folders, hook inside `morninger`, Prefect or Dagster | Reuses existing pieces | Duplicate events and partial files; `morninger` swallows exceptions and is about 56% busy; orchestrators too heavy for one machine |

## Recommendation

Option A. It is the only option whose every link was verified on the machine, and it removes the tool surface that makes prompt injection possible.

### Selected architecture

- Trigger: one Task Scheduler task `ns_article_tick`, weekdays, every 30 minutes, "Interactive only" because auth uses the keyring.
- `article_tick.py` (operator, 0 tokens) runs, in order:
  1. `AGY_STOP` present: exit.
  2. Standing order valid (L1 and L2 only).
  3. Python `.pipeline.lock` under `C:\data`.
  4. Assert DB path equals `MONOCLE_DB_PATH`.
  5. `agy --version` equals the pin.
  6. Rebuild and hash the worker profile and CORE.
  7. Quota ledger and circuit breaker.
  8. Event: backlog of at least 50, or windows 07:30, 15:30 and 17:30.
- `article_run.py --runner agy --wave W`: prepare (unchanged `article_pack`), analyze with pool 2, then `--finish` failing loud; ingest at L2 only. DSH stays the default runner.
- Each batch is a fresh process:

```
env: USERPROFILE=HOME=<worker_home>, ANTIGRAVITY_APP_DATA_DIR=<worker_home>\.gemini\antigravity-cli,
     PYTHONUTF8=1 ; cwd = empty per-wave folder under %LOCALAPPDATA% (outside repo and OneDrive)
agy -p= --agent article-processor --model <pin> --input-format stream-json --output-format stream-json
    --print-timeout 300s --disable-slash-commands   (no --json-schema, no skip-permissions)
stdin: one NDJSON line = "## Packet\n" + task.json content
```

- Worker profile, rebuilt and hashed each tick because agy rewrites `settings.json`:
  - `.gemini/config/agents/article-processor.md` with `tools: []`, `excludeDefaultComponents: true`, `inheritCustomizations: false`; body byte-identical to `ARTICLE_SYSTEM_CORE.md`, with `core_sha` recorded in meta.
  - `settings.json` with no allow rule; optional deny-all `PreToolUse` hook.

### Per-call classifier, in order

| # | Check | Class and action |
|---|---|---|
| 1 | exit not 0 or `AGY_ERROR` | exit 3 retryable: RETRYABLE, full-jitter backoff, max 3. 429 or quota: QUOTA, open breaker to the next 5-hour mark. Else FATAL |
| 2 | stderr "print timeout" or usage 0 | TIMEOUT: kill the process tree, halve the batch, retry once |
| 3 | `cli.log` lacks `agent=true`, shows `not found, falling back`, or turn-1 input exceeds CORE plus packet plus 3k | FATAL, agent not loaded; stop the lane |
| 4 | Model in `init` differs from the pin | FATAL |
| 5 | Any `step_type == tool` or non-empty `denied_actions` | VIOLATION plus alert; 2 per wave stops the wave |
| 6 | More than one model response | Double-generation warning |
| 7 | `salvage_records` parse fails | SOFT_FAIL, retry |
| 8 | Domain validation fails | PARTIAL, then `--repair` |
| 9 | OK | `safe_atomic_write` output and meta, `agy_calls` row, ledger |

### Domain gate before `--finish`

- Returned `i` set matches the packet exactly.
- `e[1]` is one of 11 codes: TIC, COM, PER, FND, IDX, EXC, IND, GEO, THM, AST, INS.
- `e[0]` appears verbatim in the title or paragraphs, except IND.
- `c` is in range with at least 2 distinct indices; `sn` and `ts` enums and `im` length hold.
- If the source has diacritics and `s` or `im` lost them, reject the record; D2 observed the model dropping diacritics.
- `meta.json` exists, `core_sha` matches, and one wave has one runner.
- Broken rate counts parse failures, validator rejections and dropped fields; the existing 10% stop threshold stays.

### Autonomy ladder

| Level | Behaviour | Promotion condition |
|---|---|---|
| L0 | Operator types `article_run.py --runner agy --wave W` | A/B passes and 3 clean L0 waves |
| L1 | Tick prepares and analyzes, stops before DB ingest; operator runs `--finish` | Standing order and 5 clean waves |
| L2 | Tick runs `--finish` and ingest; xlsx delivery stays manual | None |

- A standing order is an operator file that expires within 7 days. Its hash goes into each wave's meta, and creating or renewing it writes a harness trace.
- Kill switch `AGY_STOP` is checked before each batch. L2 falls back to L0 after 2 consecutive broken waves.
- A dead-man alert fires after 24 hours without a successful wave while backlog is at least 50. An agy version drift darkens the lane and alerts.

### Quota guard

- agy reports neither pool size nor cost, so percentage ceilings were not usable. The council proposed an absolute ledger ceiling over a sliding 5-hour window and per day, starting at 3M tokens per day.
- A 429 opens a durable circuit breaker until the next 5-hour mark. Each tick starts with one canary batch that also confirms `agent=true`.

### Governance path (WIP = 1)

| Step | Id | Content | Gate |
|---|---|---|---|
| 1 | Intake #25 | Tier 3; register ADR-0008 and ADR-0009 in harness.db `decision` (only 0001, 0002, 0006 existed) | None |
| 2 | ADR draft "0010" | Single-turn zero-tool agy runner; amend Q1 and ADR-0009 §2.3; reactivate ADR-0008 §2.2 and §2.6; confirm ToS and sending article content to Google | H1 human approval |
| 3 | US-025 | `--finish` fails loud, shared Python `.pipeline.lock`, DB path assert, disable `news_cron`, fix `settings.yaml` | None |
| 4 | Spike A/B (scratch) | A: 3 commands for profile, agent, hook overhead. B: 2 commands for real batches of 50 and 100 | None |
| 5 | US-026 | `agy_runner.py` and `--runner agy` at L0, provenance, `token_ledger --source agy`, `agy_calls`, fake-agy fixtures; A/B on about 200 articles versus DSH | Rule 07 §4 checklist |
| 6 | US-027 | `article_tick.py`, Task Scheduler, standing order and quota guard at L1 | H2 operator writes the standing order |
| 7 | None | L1 to L2 after 5 clean waves | H3 |

- A/B pass criteria for US-026, part 1: parse_fail below 2%, DoD at least 99% after repair, wrong group codes below 5% before repair.
- A/B pass criteria for US-026, part 2: BOTH rate within 5 points of DSH, tokens within ±20% of forecast, blind review of 20 articles.
- Adding field `m` (materiality) was split out as a separate contract intake. `_sort_key` (`user_output.py:287-297`) read only nested `materiality.score`, so the top-level fallback was dead code [V].

### Residual risks

1. Prompt injection from articles; mitigated by profile isolation, empty allowlist, `tools: []`, deny-all hook and VIOLATION fatal after 2. Steered content is caught only by the validator and DoD.
2. Shared quota exhaustion blocking interactive work; mitigated by an absolute ceiling and breaker.
3. agy self-update breaking flags (1.2.7 to 1.2.9 in 2 days); the profile redirection is undocumented. Mitigated by pin, canary and runbook.
4. Data egress and ToS; to be settled in the ADR before production-scale runs.
5. False success; mitigated by the classifier.
6. DB split-brain and OneDrive conflicts; assigned to US-025.
7. Two runners writing one wave; mitigated by a shared lock and runner stamp in the manifest.
8. No run while logged off (keyring auth); accepted with "Interactive only".
9. Gemini Flash-low quality unproven at scale (only 15 plus 10 articles); A/B mandatory.
10. Silent model change; assert the model in `init` and record it in meta.

## Outcome

- Decided. The runner design was adopted as ADR-0011 (accepted 2026-09-25, operator approval), implemented under US-028. The proposal's "ADR 0010" draft number was taken by ADR-0010, which retired the L1/Gold lane on 2026-09-23.
- ADR-0011.D5 rejected every token ceiling, so the proposed 3M tokens per day quota ceiling was not adopted. Tokens are recorded, not gated.
- Reconstructed 2026-10-06: the mapping of the draft ADR number to ADR-0011 and the D5 note come from the ADR-0011 frontmatter and body, not from this proposal's original text.
