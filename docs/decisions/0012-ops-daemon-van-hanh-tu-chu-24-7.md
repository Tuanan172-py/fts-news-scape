---
id: ADR-0012
type: adr
title: Autonomous ops daemon while the machine is on; ops_daemon, DBOS workflows, Telegram oversight
status: accepted
lane: high-risk
created: 2026-10-01
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
approvers: [operator 2026-10-01]
story: [US-029]
amends: [ADR-0011]
related: [ADR-0010, ADR-0008, ADR-0014]
evidence:
  - commit:579163c
  - commit:4e461cd
  - path:plans/20261001-1100-autonomous-ops-24x7/plan.md
  - path:docs/proposals/20261001-ops-council.md
  - path:project/docs/operations/ops-daemon.md
  - path:project/src/ops/dbos_flow.py
  - path:project/scripts/ops_install.ps1
  - test:project/tests/test_ops_council_fixes.py
  - test:project/tests/test_ops_core.py
  - metric:sensor pass 1.3 s by hand versus 40-396 s under Task Scheduler priority 7; 6.2 s with backlog after priority 4, 2026-10-01
  - metric:first real daemon wave W10011351 DONE, 100 of 100 articles, 2026-10-01
  - operator:approved 2026-10-01 ("đồng ý thực thi toàn bộ kế hoạch")
  - operator:council decisions D1', D8-D14 answered 2026-10-01
original: "commit:579163c"
reconstructed: 2026-10-06
summary: A deterministic Python ops_daemon with DBOS workflows, ops.db state, sensors, provider breakers, timeouts and Telegram oversight runs Article Lane waves while the machine is on; autonomy is L0 or L1 after the council amendment.
summary_vi: Daemon vận hành tất định bằng Python, workflow DBOS, trạng thái ops.db và Telegram tự chạy đợt Article Lane khi máy mở; chỉ còn mức L0 và L1.
---

# ADR-0012 — Autonomous ops daemon while the machine is on; ops_daemon, DBOS workflows, Telegram oversight

## Context

Measured on 2026-10-01:

- All end-to-end stages already ran.
- `morninger` was started by hand. It died on reboot or logoff.
- `article_tick.py` (ADR-0011) was not scheduled anywhere.
- No heartbeat and no operational alerting existed.
- No durable wave state existed: a crash mid-wave lost track of the wave.
- The operator had to be present to trigger each wave.

The plan `plans/20261001-1100-autonomous-ops-24x7/plan.md` compared workflow engines and human channels for one Windows machine. A six-position review council (`docs/proposals/20261001-ops-council.md`) then found seven blocking items (B1 to B7) and asked the operator to decide D1' and D8 to D14. The original title said "24/7"; the amendment below limits operation to the time the machine is on.

## Decision

The amendment history at the end of this section overrides D1 (24/7 scope), D5 (L2, L3 and approval buttons) and the approval parts of D9.

- D1. The control plane is deterministic Python with 0 tokens (`project/src/ops/`), running one process `ops_daemon.py run`.
  - Task Scheduler keeps it alive with two triggers: at logon, and a 5-minute repeat as watchdog.
  - The task runs under the user account, because agy reads credentials in the user profile, which Session 0 cannot see.
  - agy MUST NOT act as the orchestration loop.
- D2. The durability layer is DBOS 3.x on a separate SQLite file `C:\data\news-scape\ops_dbos.db`.
  - Each wave is a workflow `wave-<code>[-r<n>]`; each step is a checkpointed step.
  - `application_version` is pinned (`ops-v1`), because DBOS only recovers workflows of the same version.
  - A spike on this machine passed: killing mid-step 2 did not rerun step 1, reran step 2, and the same id returned the old result.
  - Steps are at-least-once, so `prepare` skips when the manifest exists and `analyze` switches to `--repair` when output exists. Finished batches never spend tokens again.
- D3. Operational state lives in `C:\data\news-scape\ops.db`: `ops_events`, `ops_alerts` (outbox), `provider_breakers`, `ops_state`, `ops_waves`, `ops_commands`.
  - The `monocle.db` schema MUST NOT change.
  - Events are also written as JSONL copies under `ops_logs/`.
- D4. A sensor runs every 2 minutes on its own thread. Scope: pending articles of today and yesterday, using the selector `article_pack.load_candidates`. A wave opens when one rule holds:
  - T1: at least 100 pending articles.
  - T2: the oldest pending article is older than 90 minutes, applied only 06:00 to 22:00.
  - T3: a sweep window is reached.
  - One wave at a time (wave WIP = 1). A wave takes 100 articles in batches of 50. Backlog older than the scope is only reported, never processed automatically.
- D5. An autonomy ladder L0 to L3, set by a standing order valid at most 7 days. A missing or expired order returns to L0.

  | Level | Daemon behaviour |
  |---|---|
  | L0 | Report only, with a **Run wave** button |
  | L1 | After analysis, wait for a **Load DB** button; after 120 minutes the wave is PARKED |
  | L2 | Run `--finish` automatically |
  | L3 | Also deliver the xlsx |

  - Two consecutive failed waves drop one level. Five consecutive clean waves only suggest a level up; a human decides.
- D6. Durable circuit breakers per provider.
  - Error classes: AUTH, QUOTA, NETWORK, TIMEOUT, EMPTY.
  - AUTH stays open until a human resets it. QUOTA opens for 5 hours. NETWORK and TIMEOUT open after 3 consecutive errors.
  - When the open period ends, the breaker goes HALF_OPEN and retries. Waves PARKED for a provider resume when the breaker allows.
  - Provider switching follows the standing order: `never` (default), `ask` or `auto`.
  - No token ceiling: the 3M tokens per day quota guard of the 2026-09-23 council is rejected because it contradicts ADR-0010.
- D7. Layered timeouts.
  - One agy call: 600 s, already in the runner.
  - Step deadlines: analyze 45 minutes, finish 10 minutes, other steps per `config/ops.yaml`.
  - Analyze progress idle for more than 25 minutes counts as hung.
  - On timeout the whole process tree is killed.
- D8. Death detection uses three independent signals: a local heartbeat every 60 s; an off-machine healthchecks.io ping (dead-man); edge probes for fresh capture, DB writability, disk, rising dead-letter and standing-order expiry.
- D9. Human in the loop.
  - A Telegram bot uses long polling, accepts commands only from whitelisted `chat_id`, and sends only operational metadata.
  - The console `ops_console.py` opens with Ctrl+Alt+O in the Windows Terminal quake window.
  - Radar gains an autonomous-operations section.
  - Every human command becomes a `human.command` event.
- D10. `ops-sentinel` (agy, single turn, no tools, draft) diagnoses on request. It only proposes one whitelisted command, as a button.

### Amendment history

**2026-10-01, after the review council (in force; replaces conflicting items above).** Source: `docs/proposals/20261001-ops-council.md` §2 (blocking items B1 to B7) and §9 (operator decisions D1', D8 to D14).

- Operating model (D9, D10 of the council). No 24/7 operation. The daemon runs while the machine is on; when it sleeps or shuts down, everything stops and articles wait.
  - Disabling sleep, auto-logon and Defender exclusions are dropped.
  - The primary dead-man is a local watchdog task (`ops_daemon.py watchdog` every 5 minutes). It alerts only when the heartbeat is stale on two consecutive checks, so sleep causes no false alarm. healthchecks.io becomes optional.
- The autonomy ladder keeps only L0 and L1.
  - L0 only measures and reports.
  - L1 opens a wave when conditions hold and runs it through DB ingest with no per-wave approval gate. This matches the ADR-0008 amendment: "không dựng lại cổng hỏi người dưới bất kỳ tên nào". State `AWAIT_APPROVAL` and commands `/approve`, `/reject` are removed.
  - An old command file saying L2 or L3 is read as L1.
  - `article_tick.py` (ADR-0011) still reads L1 as "analyse only". The daemon command file says L1, so a manual `article_tick` run stays safe by not loading the DB. `article_tick` is no longer scheduled.
- Delivery (council D11) is outside the wave lifecycle. The DB is the source of truth; delivery is a separate per-user process under its own story.
- Data (council D8). Full cleaned article text MAY be sent to every provider. Packets carry only `i/t/p`. Internal data (logs, config, secrets) MUST NOT travel in payloads. Every event, alert and `ops-sentinel` context passes through `src/ops/redact.py`.
- Fixes to blocking items:

  | Code | Fix |
  |---|---|
  | B2 | `ops_wave_articles` reserves articles for waves not DONE or CANCELLED; the sensor and `article_pack --exclude-file` skip reserved articles |
  | B3 | Step processes start suspended, attach to the daemon Job Object `KILL_ON_JOB_CLOSE`, then run (bypassing the venv launcher job `SILENT_BREAKAWAY_OK`) |
  | B4 | `ops_article_attempts`; an article packed `max_attempts_per_article` times is not retried automatically |
  | B5 | `redact()` masks the Telegram token, healthchecks URL, `sk-` keys and Bearer tokens before every write and in Telegram send errors |
  | B6 | `--finish` ignores AGY_STOP and `/cancel` midway; the stop flag is read only at the boundary before ingest. The agy ledger replaces old rows on rerun |
  | B7 | The workflow catches step exceptions and settles FAILED; the daemon reconciles workflows at every sensor tick (`APP_VERSION = ops-v2`) |
  | R2 | Telegram accepts only private chats whose `from.id` matches a listed chat id; the bot config never adds groups; privilege-raising commands need confirmation |

- Load on the operational DB. The sensor never reads content columns and does not measure during a wave. The write probe does not run during a wave.
- Two defects that appeared only under Task Scheduler:
  - Priority. Tasks default to priority 7 (low CPU and I/O priority), inherited by every child. A sensor pass took 1.3 s by hand but 40 to 396 s inside the task. `ops_install.ps1` now sets `-Priority 4`; a pass with backlog then took 6.2 s.
  - agy path. The user PATH stores `%LOCALAPPDATA%\agy\bin` unexpanded, so bare `agy` raised WinError 2 (wave W10011351, 0 tokens). `agy_runner.resolve_agy()` searches `AGY_BIN`, PATH, expanded PATH, then the install location.
- Evidence: `tests/test_ops_council_fixes.py` (tests named B2 to B7, R2, D9, D10).

**2026-10-01, ADR-0014.** The 7-day standing order of D5 is replaced by a 30-day mandate that renews itself under health conditions (ADR-0014.D4).

## Alternatives

| Option | Why rejected |
|---|---|
| Prefect 3 | Needs a server, a worker and a UI; kept as option 2 only if a ready UI were needed (reconstructed from plan §3.1). |
| Temporal | The single-process build is only a dev server; too heavy for one machine (reconstructed from plan §3.1). |
| Restate, Dagster sensors | Restate adds another runtime to maintain; Dagster is asset-oriented and weak on human-in-the-loop (reconstructed from plan §3.1). |
| Inngest, Hatchet, Windmill, n8n | Need Docker, Node or Postgres; the Windmill Windows worker is paid (reconstructed from plan §3.1). |
| APScheduler 3.x with a hand-written lease table | Durable schedules only, no in-wave progress; in effect rewriting half of DBOS. Kept as fallback if the DBOS spike failed (reconstructed from plan §3.1 and §3.2). |
| Agent frameworks with built-in approval (LangGraph, OpenAI Agents SDK, CrewAI and others) | Their approval sits inside the agent tool loop. Here the agent is a zero-tool single-turn function (ADR-0011), so approval belongs to the workflow layer (reconstructed from plan §3.1). |
| Run 24/7 with sleep disabled, auto-logon and Defender exclusions | Weakens company machine security; the operator chose operation while the machine is on (council D9, R9). |
| A human approval gate before `--finish` (original L1) | Contradicts the ADR-0008 amendment and becomes rubber-stamping; the DoD gate decides DB ingest (council §4, operator D10). |

## Consequences

- New dependencies `dbos` and `psutil`.
- `build_sandbox_profile` gains parameters `agent_name`, `description`, `instruction_guard`; defaults keep the old behaviour.
- While the daemon lives at L1 or higher, radar does not propose opening waves by hand.
- `article_tick.py` still runs by hand and shares `.pipeline.lock` with the daemon.

### Current status (2026-10-06)

- In force with the amendments above. The daemon `news-scape-ops` and watchdog task are installed at priority 4.
- The L1 grant of 2026-10-05 10:40 dropped back to L0 after two failed waves (W10051042, W10051050) caused by stale packets of ADR-0018 (`docs/OPEN-ITEMS.md` OPS-1).
- A restart fix waits for a stale `ops_daemon.lock` for 45 s (commit 4e461cd, US-029). `ops-sentinel` is still draft.

## Rollback

- Immediate stop: `/stop`, or create `C:\data\news-scape\AGY_STOP`.
- Full removal: `scripts\ops_install.ps1 -Uninstall`.
- The pipeline returns to manual operation through `article_run.py`. No data in `monocle.db` depends on `ops.db`.

## Follow-up

- [x] Council fixes B2 to B7 and R2 with regression tests (`tests/test_ops_council_fixes.py`).
- [x] First real wave through the daemon, W10011351, DONE with 100 of 100 articles.
- [ ] Operator grants L1 again once stability conditions hold (`docs/OPEN-ITEMS.md` OPS-1, OPS-3).
- [ ] Per-user xlsx delivery as its own story (council D11).
- [ ] About 10.9 thousand backlog articles outside `lookback_days`: separate operator task.
- [ ] `ops-sentinel` to active after 10 real diagnoses (rule 07).
