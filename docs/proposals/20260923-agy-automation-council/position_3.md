# Position 3: Operations, trigger & governance red team

**Verdict.** Ship agy in stages, in this order: L0 manual runner, then L1 scheduled prepare+analyze with a manual finish, then L2 fully automatic. Each stage waits on ADR 0010 and three fixes to the existing pipeline. Don't hook morninger, and don't let the agent hold tools.

## 0. Corrections to the dossier (verified locally today)
- **The live DB isn't in OneDrive.** User env `MONOCLE_DB_PATH=C:\data\news-scape\monocle.db` (config.py:85-90) is live (467 MB, WAL 16:19 today). `settings.yaml:3` points to a **stale 187 MB OneDrive copy from 21/09**, so a scheduled process without the user env writes there: **split-brain**. Conflict copies exist in both `archive_conflicts/`.
- **`news_cron` is running as I write.** It started 16:11 (Last Result 267009), is "Interactive only", calls bare `python`, and is set to "No Start On Batteries". This is the live form of OPEN-ITEMS A0-5 (docs/OPEN-ITEMS.md:62-64).
- **`article_run.py` has no lock at all.** `--finish` runs `l1_ingest`/`agent_ingest`/`token_ledger` with `check=False` (article_run.py:435-450). Only `expand_rc==1` stops the wave (:430-433). Ingest failures are therefore *silent*, which breaks ADR 0008 §2.4 (0008:90-93) and plan §16.5 (plan.md:840).
- **Ledger misattribution.** `token_ledger --since` attributes DSH sessions by time window (article_run.py:419-446, token_ledger.py:198), so agy usage is invisible and concurrent DSH sessions get misbooked.

## 1. Event model and trigger topology
**Real events:**
- E1: derive checkpoint. `run_derive` → `checkpoint_reached` → silver manifest (morninger.py:229-245).
- E2: backlog of analyzable articles ≥ N.
- E3: market windows. Pre-market 07:30, post-close ~15:30, EOD 17:30.
- E4: operator command.

E1 is a hint, E2 the predicate, E3 the timing.

**Topology:**
- **One Task Scheduler entry** `ns_article_tick` runs every 30 min from 07:00 to 18:00 on weekdays. It calls a thin `project/scripts/article_tick.py` with an explicit `MONOCLE_DB_PATH` and the venv python. Settings: IgnoreNew, StartWhenAvailable, ExecutionTimeLimit 90 min, WakeToRun=false, run as the logged-on user. agy auth lives in the user profile `~/.gemini`, so logged-off runs are impossible by design.
- The tick evaluates the predicates (kill switch → standing order → lock → E2/E3 → quota) and then calls `article_run.py --runner agy` in-process as subprocess steps.
- **No morninger hook.** morninger jobs swallow exceptions (morninger.py:186-189, 224-226), which breaks fail-loud. It is also ~56% busy (OPEN-ITEMS:63), and a 20-minute agy wave on an APScheduler thread would starve capture.
- **No watchdog on OneDrive folders** (duplicate events). **No SQLite job queue yet**: file-keyed resume (`pending_batches`, article_run.py:204) already is the idempotent queue.
- **Collision.** Disable `news_cron` as part of the story (A0-5 already recommends it). The tick never scrapes, so it only competes with morninger as a DB writer: BEGIN IMMEDIATE, busy_timeout 30000 (Rule 03).
- **Locking.** Port `.pipeline.lock` (run_daily.ps1:38-70: exclusive write, FileShare.Read, pid/mode banner) to Python and have *both* `run_daily.ps1` and `article_run.py` (any runner) take it. Move the lock to `C:\data\news-scape\` so OneDrive can't touch it. Also stamp `runner`/`owner` into `wave_<W>.json`. `--finish` refuses a wave whose outputs mix runners unless `--allow-mixed` is passed. That flag is the per-wave runner mutex.
- **Quota backpressure: a budget ledger.** agy reports no cost, so book `usage.*` per call into `token_ledger` with a `runner` column (or `note='agy'` if we avoid a harness.db schema change).
  - The guard keeps rolling 5 h and 7 d sums and compares them with operator caps in the standing order. Default: at most 40% of the observed pool, leaving the rest for interactive IDE work.
  - Exit 3 `AGY_ERROR` or a quota message opens a **circuit breaker** until the next 5 h boundary. No retries inside the window.
  - Each tick starts with **one canary batch** and continues only if it comes back clean.
- **Sleep, battery and logoff.** Missed windows coalesce into one catch-up run. Interrupted waves resume via `--resume`. A Job Object (KILL_ON_JOB_CLOSE) kills orphans (#1044). The wrapper refuses a DB path inside OneDrive.

## 2. Human-in-the-loop: autonomy ladder
The ADR 0008 amendment says an explicit command *is* the approval and "no path starts itself" (0008:45). The plan forbids re-creating a confirmation gate "under any name" (plan.md:612). A schedule therefore needs a **standing order**: an operator-created, expiring file `C:\data\news-scape\agy_standing_order.yaml` with `level`, `valid_until`, `max_items_per_day`, `quota_cap_pct` and `model`. Creating that file is the explicit command. It is not a per-run question. If the file is missing or expired, the tick does nothing.

| Level | Starts itself? | Scope | Exit criterion |
|---|---|---|---|
| **L0** | No | Operator runs `article_run.py --runner agy --wave W [--finish]` | 3 clean waves: DoD ≥99%, parse_fail <2% (plan.md:523-531) |
| **L1** | Yes (standing order) | prepare + agy analyze + expand dry-run. **Stops before DB load** and notifies "wave W ready" | 5 consecutive clean scheduled waves |
| **L2** | Yes (standing order) | Full finish with automatic gates. Delivery (xlsx) stays manual | Ongoing |

L1 is time-boxed commissioning, not a cost gate (consistent with Q4).

**Kill switches:**
- The file `C:\data\news-scape\AGY_STOP` is checked before every batch.
- **Auto-demotion:** L2 drops to L0 after 2 consecutive waves with DoD <95% or parse_fail >10%. This mirrors the rollback rule (plan.md:568).

**Gates that must remain (all automatic):**
- Prefix-hash mismatch stops the wave.
- parse_fail >10% stops the wave before DB load (article_run.py:430).
- Child rc≠0 stops the wave. This **needs the `check=False` fix first**.
- DoD for L1 and Gold, plus the four Gold reject rules (plan.md:842).
- Gold value gate (ADR 0004) and subscriber gate (ADR 0005).
- Delivery stays outside automation.

## 3. Failure, alerting and observability
- **Classifier per call:**
  - OK
  - SOFT_FAIL: exit 0 but no `structured_output`, or `denied_actions` non-empty (#794)
  - TIMEOUT: usage all zero or stderr "print timeout"
  - RETRYABLE: exit 3 retryable, or #902 CANCELED/empty
  - QUOTA: breaker opens
  - FATAL: exit 1/2, version mismatch, schema invalid
  - Poison a batch after 3 tries.
- **Per-call rows** in a local `agy_calls` table (C:\data\news-scape): conversation_id, version, model, exit, usage, denied_actions, class.
- **Per wave:** one **Detailed trace** in harness.db (TRACE_SPEC.md:93, including `intake_id`, `error_msg`, `intervention`) and one `token_ledger` row with runner=agy.
- **Alerts:**
  - Existing `src/notifier/file_notify.py` plus a Windows toast (Teams webhook optional: second egress).
  - Alert on: FATAL, breaker open, auto-demotion, `denied_actions` ever non-empty, and "no successful wave for 24 h while backlog > N" (the dead-man check the negative consequence at 0008:119-121 asks for).
- **Idempotency:** write outputs with `safe_atomic_write` and a header `{runner, model, agy_version, prefix_hash}`. Skip a batch whose output already exists. Parameterize provenance, currently hard-coded as `AGENT_PROVIDER/MODEL_USED` at article_expand.py:53-54.

## 4. Governance path
- **Tier 3 high-risk.** Hard gates: external provider/account, the scheduler flow flag, agent-handoff provenance (data contract), and Harness Core (AGENTS.md:16-17, FEATURE_INTAKE.md:33-38). Precedent is ADR 0009.
- **IDs:** next intake **#25** (max 24). Next story **US-025**, since US-024 is `implemented`. Next ADR **0010**. No story is `in_progress`, so WIP=1 is free. US-020/022/023 are deferred and US-021 is planned.
- **Registry drift:** harness.db `decision` registers only 0001/0002/0006. Register 0008/0009/0010.
- **ADR 0010 skeleton: "agy làm runner thay thế cho article_analyze & kích hoạt theo lệnh thường trực".**
  - *Context:*
    - ADR 0009 §2.7 keeps agy as an alternative runner (0009:62-63).
    - Q1 says in-process PTC, not headless (plan.md:110, 614).
    - The ADR 0008 amendment has "no path starts itself".
    - Dossier §A facts.
  - *Decision:*
    1. Amend Q1: headless is allowed **only** for `--runner agy`, one-shot, **zero-tool**. The prompt is passed over stream-json, and output is read from `structured_output` only. The four invariants hold (plan.md:275-280).
    2. Amend ADR 0009 §2.3: allow the model allow-list `gemini-3.8-flash-*`, pinned per standing order.
    3. Amend ADR 0008: revive §2.2 (never `--dangerously-skip-permissions`) and §2.6 (pin plus version check). Define the standing order as an explicit command. Add the L0/L1/L2 ladder and the kill switch.
  - *Consequences:* shared quota, egress to Google, second provenance value, ledger growth.
- **Rule 07 §4 checklist:**
  1. Tier recorded in ADR 0010.
  2. `registry.yaml` entry `article-processor` gets a `runners: [dsh, agy]` or a separate id, plus SKILL.md.
  3. `pipeline.yaml` stage `article_analyze` gets a runner/trigger policy.
  4. US-025 with proof: fake-agy fixtures for each failure class, a lock test, added to the AUTOMATION_CLIS test.
  5. KPIs via `harness_cli.py metric`, plus a ledger row per wave.
- **Without approval:** scratchpad spikes on *copies* of task.json, read-only DB (note: spikes already send news text to Google). **Needs approval:** anything touching the repo, scheduler, DB or `.agents/`.

## 5. Red team of the prior draft (dossier §E)
- **stdin text mode:** refuted, since `-p` ignores stdin. Use `-p=` with stream-json.
- **`--dangerously-skip-permissions`:** breaks ADR 0008 §2.2, and it is pointless for a zero-tool call. Deny all tools instead.
- **25 articles per batch:** with ~11.7k fixed tokens per call, that is ~470 tokens per article of overhead, against ~117 at 100 per batch. Measure it and don't assume.
- **"Compact JSON":** irrelevant to agy (SESSION-LATEST:49).
- **Adding `m`:** a separate contract change.
- **Story US-024:** the id is already taken.
- **gemini-3.8-flash-low:** has no quality evidence against DoD ≥99%.
- **Missing:** trigger, lock, quota, kill switch, provenance, ledger. Inherits `auto_pilot.py:180-189` agent-reads/writes-files, violating Rule 01 §1.

## 6. Top 10 risks and mitigations
1. **Prompt injection from scraped articles.** Article text could carry instructions, and the agent has ~55 tools, a broad `permissions.allow`, the repo listed in `trustedWorkspaces`, and `artifactReviewPolicy: always-proceed`.
   - Run with cwd set to an empty temp directory **outside** the repo and outside trusted workspaces.
   - Use a custom agent with `tools: []` and `excludeDefaultComponents`, plus a PreToolUse deny-all hook as belt and braces.
   - Pass `--disable-slash-commands`.
   - Treat any `denied_actions` as FATAL plus a security alert.
   - Keep data JSON-framed. Validate citations by index against `p[k]`.
2. **Quota exhaustion starving interactive work.** Budget ledger, cap percentage, breaker, off-peak windows, canary batch.
3. **Self-update breaking flags or output.** At tick start, `agy --version` must equal the pinned version, or the tick refuses and alerts. Run a schema canary. Keep the `.old` exe for rollback.
4. **Data egress and ToS.** News text and packet ordering (which reveals watchlist interest) go to Google.
   - Confirm account type, data-use terms and whether automation is permitted (consumer Pro vs FPTS domain); record in ADR 0010 before real-data runs.
5. **Silent SUCCESS** (#794, #902, timeout). Use the classifier from §3, never trust `status`, and always pass `--print-timeout`.
6. **DB split-brain and OneDrive conflicts.** Assert the resolved DB path, keep the lock and job state local, and in the long run move `agent_tasks/outputs` off OneDrive.
7. **Dual-runner races, double ingest, misattributed ledger.** Global lock, per-wave runner mutex, runner-keyed ledger rows (fix the `--since` attribution).
8. **Repo `.agents/` auto-loaded into agy context** (up to 20k tokens of rules). Out-of-repo cwd fixes it; verify via `input_tokens`.
9. **Runaway automation.** A re-pack loop or poison batches could keep burning quota. Controls: poison after 3 tries, `max_items_per_day`, standing-order expiry, `AGY_STOP`, auto-demotion.
10. **Model drift or silent substitution.** `--conversation` falls back to the default model, and model names churn.
    - Pin `--model`, record it in provenance, keep DoD gates plus a weekly 20-article sample audit.
