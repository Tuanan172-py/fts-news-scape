---
id: ADR-0011
type: adr
title: Antigravity CLI (agy) runner and headless conductor for Article Lane
status: accepted
lane: high-risk
created: 2026-09-25
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
approvers: [operator 2026-09-25]
story: [US-028]
amends: [ADR-0009]
related: [ADR-0010]
evidence:
  - commit:dd1e709
  - commit:8ec12f8
  - path:docs/proposals/agy-automation-council-2026-09-23.md
  - path:docs/proposals/agy-council-2026-09-23/spike2-RESULTS.md
  - path:project/src/agent/agy_runner.py
  - path:project/scripts/article_tick.py
  - test:project/tests/test_agy_runner.py
  - test:project/tests/test_article_tick.py
  - metric:custom agent in worker profile cut input 24.9k to 13.6k tokens per call (-45%), spike 2026-09-23
  - metric:Windows argv ceiling 32,767 characters, 32,800 fails with WinError 206, council F2
  - operator:approved 2026-09-25 after the 2026-09-23 architecture council
original: "commit:dd1e709"
reconstructed: 2026-10-06
summary: Adds a headless agy runner beside DSH; Python conducts, agy is a stateless zero-tool single-turn function in an isolated worker profile, fed by stdin stream-json, validated in Python, triggered by article_tick.py, with no token ceiling.
summary_vi: Thêm runner agy chạy headless song song DSH; Python điều phối, agy là hàm nhận thức một lượt không tool trong hồ sơ cô lập, không trần token.
---

# ADR-0011 — Antigravity CLI (agy) runner and headless conductor for Article Lane

## Context

- Since ADR-0010 (2026-09-23), Article Lane is the only processing path. `article-processor` ran through the DeepSeek Harness (DSH) web interface.
- DSH blocked unattended operation in four ways:
  - Headless incompatibility. The DSH Conductor runs in a browser. The operator had to paste `wave_<W>.conductor.ts` into `run_code`. No schedule at market windows (07:30, 12:30, 15:30, 17:30) was possible.
  - Sandbox writable roots. DSH writes only inside the repository or a temp folder, while the production DB lives at `C:\data\news-scape\monocle.db`, outside OneDrive sync.
  - Load at mount (rule 09). DSH loads the preset when the host starts; config edits without a host restart drift silently.
  - Subscription model. The project uses a paid Antigravity account with a "Work Done" pool refreshed every 5 hours. It is metered by session quota, not per token.
- A three-position architecture council with two spikes evaluated agy automation on 2026-09-23 (`docs/proposals/agy-automation-council-2026-09-23.md`). It verified that `agy -p` ignores stdin in text mode and that `--json-schema` conflicts with zero tools (council F1, F8).

## Decision

- D1. Dual-runner Article Lane. Add runner `agy` (model `gemini-3.8-flash-low`) beside the default runner `dsh` (`deepseek-flash`). `dsh` serves supervised interactive sessions; `agy` serves unattended headless waves.
- D2. Stateless pure cognitive function. Python is the conductor (0 tokens, deterministic). `agy` is a single-turn function, prompt in and JSON out, and MUST NOT be granted any tool (`tools: []`). This removes prompt-injection risk and background-process bugs #1044 and #902.
- D3. Isolation through a sandboxed worker profile:
  - Each automated wave creates its own profile at `%LOCALAPPDATA%\news-scape\agy_profiles\<wave>\`.
  - The profile has an empty `permissions.allow: []` and MUST NOT inherit the main user's shell permissions.
  - A global custom agent with `excludeDefaultComponents: true` embeds `project/data/prefix/ARTICLE_SYSTEM_CORE.md` verbatim. This cuts fixed token overhead by 45% without trimming article content.
  - A `PreToolUse` hook denies every unexpected tool call.
- D4. I/O protocol:
  - Article data goes through stdin as `stream-json` (one-line NDJSON), bypassing the Windows command-line limit of 32,767 characters.
  - The `--json-schema` flag MUST NOT be used, because agy implements it with a hidden `finish` tool that conflicts with `tools: []`.
  - Python extracts results with `salvage_records`, validates JSON Schema and checks the domain: 11 group codes, Vietnamese diacritics, citation index range.
- D5. No token ceiling:
  - Every proposal for a daily token ceiling, word ceiling or character limit that trims articles or stops a wave is rejected.
  - Tokens are only recorded in `token_ledger` and wave metadata for ROI and performance audit.
  - Batch size for `agy` is fixed at 50 articles per batch, for network stability and response time.
- D6. Headless conductor with a hybrid trigger:
  - `scripts/article_tick.py` runs periodically from Windows Task Scheduler.
  - It opens a wave when at least 50 articles are pending (fast path) or at a market closing window (07:30, 12:30, 15:30, 17:30).
  - Safety: a single-process lock `.pipeline.lock` and an emergency stop flag `AGY_STOP`, both in `C:\data\news-scape\`.

## Alternatives

| Option | Why rejected |
|---|---|
| Earlier draft: stdin `--input-format text`, `--dangerously-skip-permissions`, array schema with `prefixItems`, batch 25 | Stdin is ignored in text mode (F1); skipping permissions breaks ADR-0008 §2.2; the schema returns HTTP 400 (F8) (reconstructed from the council proposal §4). |
| Fully autonomous conductor where agy decides which scripts to run | Violates rule 01 §1 and rule 07; bugs #1044, #902, #1077; prompt-injection risk from articles with 57 tools and a `.py` allowlist (reconstructed from the council proposal §4). |
| MCP pull-worker (claim and submit) | Works without skipping permissions, but took 7 turns and 96.5k tokens for 3 articles, about 2.5 to 30 times one-shot. Its own proponent withdrew it (reconstructed from the council proposal §4). |
| Long-lived multi-turn `stream-json` worker | Context grows, batches leak into each other, and in-conversation cache does not repay the cost (reconstructed from the council proposal §4). |
| Sidecar, `agentapi` or remote-control | Requires the Antigravity app running and manual enabling; remote-control is a human UI only (F10) (reconstructed from the council proposal §4). |
| Daily quota guard of 3M tokens with an absolute ceiling | Proposed by the council (§3.5) but contradicts ADR-0010.D5; rejected in D5 of this ADR. |
| Prefect or Dagster as scheduler; a hook inside `morninger`; a watchdog on the OneDrive folder | Too heavy for one machine; the `morninger` job swallows exceptions and was about 56% busy; OneDrive events are duplicated and partial (reconstructed from the council proposal §4). |

## Consequences

- `article_run.py` accepts `--runner {dsh,agy}` and an `--analyze` flag that automates the `agy` run.
- `article_expand.py` detects provenance from the metadata file (`agent_provider="agy"`, `model="gemini-3.8-flash-low"`).
- Data written to `monocle.db` follows the current data contract through the two DoD gates `l1_ingest` and `agent_ingest`.
- Pacing: at most 100 articles per wave (2 batches of 50), to avoid exhausting the 5-hour Antigravity session quota.

### Current status (2026-10-06)

- The agy runner, worker profile and zero-tool principle remain in force. ADR-0017 makes agy the reference runner for the unified output contract.
- D6 is amended by ADR-0012: `ops_daemon` replaced the scheduled `article_tick.py`, which still runs by hand and shares `.pipeline.lock`.
- The dual-runner split of D1 generalized: DSH, agy, opencode and OpenRouter are interchangeable runtime options (FACT-llm-runtimes-are-interchangeable).

## Rollback

- Trigger: the `agy` runner fails technically, or its DoD pass rate falls below 90% in two consecutive waves.
- The operator creates the flag file `C:\data\news-scape\AGY_STOP` to pause the background trigger.
- The system continues through the default runner with `article_run.py --runner dsh`. Silver data and core code are not affected.

## Follow-up

- [x] `agy_runner.py`, `--runner agy`, provenance in `article_expand.py`, `token_ledger` source (commit dd1e709).
- [x] `article_tick.py` with lock and `AGY_STOP` (commit dd1e709).
- [x] Unattended scheduling moved to `ops_daemon` (ADR-0012).
- [ ] Confirm agy version pinning and the model assertion against silent model changes (council risks 3 and 10); their status is not recorded in this ADR.
