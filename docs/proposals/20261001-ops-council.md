---
id: PRP-20261001-ops-council
type: proposal
title: Review council for autonomous 24/7 operations with human in the loop
status: decided
lane: high-risk
created: 2026-10-01
updated: 2026-10-06
lang: en
authors: [ops council (6 members), An Pham Thanh]
adr: [ADR-0012, ADR-0014]
story: [US-029, US-031]
related: [ADR-0008, ADR-0010, ADR-0011]
evidence:
  - path:plans/20261001-1100-autonomous-ops-24x7/plan.md
  - path:docs/proposals/20261001-ops-council/position_1_kien-truc.md
  - path:docs/proposals/20261001-ops-council/position_4_red-team.md
  - path:docs/proposals/20261001-ops-council/position_6_toi-gian.md
  - commit:579163c
  - metric:src/ops grew from 7 to 16 modules (about 3,600 lines) during the 30-minute review, 2026-10-01
  - metric:one sensor pass took 262.6 s on a 2-minute cycle at L0, 2026-10-01
  - metric:10,944 articles outside the automatic scope (implementation report said 5,908), 2026-10-01
  - metric:611 tests passed (1 real-DB test skipped); wave W10011351 DONE 100/100, 2026-10-01
  - operator:D1', D8-D14 answered 2026-10-01
original: "commit:579163c"
summary: Should the uncommitted ops daemon run Article Lane waves autonomously? Council kept the direction, raised seven blockers B1-B7, removed the per-wave approval gate; operator accepted, ADR-0012 and ADR-0014 followed.
summary_vi: Hội đồng giữ định hướng daemon vận hành tự chủ, nêu 7 mục chặn B1-B7, bỏ cổng duyệt từng đợt; người vận hành chốt, dẫn tới ADR-0012 và ADR-0014.
---

# PRP-20261001-ops-council — Review council for autonomous 24/7 operations with human in the loop

## Question

- Can the plan `plans/20261001-1100-autonomous-ops-24x7/plan.md` and the uncommitted code in `project/src/ops/`, `project/scripts/ops_*.py` and `project/config/ops.yaml` run Article Lane waves without an operator?
- If yes, which defects block it, and where must the human sit in the loop?
- Scope: read-only review by six independent members.
  - (1) architecture and durability, (2) governance and invariants, (3) human in the loop and operator experience.
  - (4) red team for security and failure modes, (5) code audit against the plan, (6) minimalist critique.
- Working papers: [20261001-ops-council/](20261001-ops-council/).
- Label `[checked]` means the chair re-verified the claim against code after the member report.

## Findings

### Executive conclusion

- All six members agreed on the direction: a deterministic Python control plane at 0 tokens owns clocks, timeouts and kills.
- agy MUST NOT be the orchestration loop, because it dies together with the incident it should report.
- The observation layer (P1) comes before automation. The 3M quota guard is dropped because it contradicts ADR-0010.
- `ops.db` is separate from `monocle.db`; the `monocle.db` schema is unchanged.
- The process broke the Hard Gate. The plan said "no code yet" and "ADR 0012 before code". During the review another session wrote `project/src/ops/` to 16 modules, about 3,600 lines, covering P1 to P5.
- That session installed DBOS 3.2.0 before the P0 spike and cited "ADR 0012" before the ADR existed. A second work stream (diffs to `openrouter_runner.py` and `agy_runner.py`) and story US-030 broke WIP=1.
- The core promise "no re-spending of tokens" (plan §3.2) was false in code. At least three paths re-analyze the same articles: A1, A2/A3 and C5.
- The L1 approval gate sat in the wrong place and contradicted the ADR-0008 amendment of 2026-09-18: "Không dựng lại cổng hỏi người dưới bất kỳ tên nào" [checked, `docs/decisions/0008-*.md:49`].
- The approval message carried only counts, so the approver had no basis to reject. Truly external actions (xlsx delivery, failover to OpenRouter, standing order extension) needed one tap and no evidence.
- The Telegram channel was at risk: Vietnam requested blocking from 05/2025 (position_4 R1). The bot checked only `chat.id`, and `/level L3` and `/failover auto` ran on one tap.

### Blockers (must be fixed before the daemon runs above L0)

| Id | Finding | Evidence | Fix |
|---|---|---|---|
| B1 | Code before ADR; code grew during review; second work stream outside the story. | `git status`: `src/ops/` untracked, `docs/decisions/` stopped at 0011 [checked] | Stop the coding session, set US-029 to blocked, split the runner diff, write an ADR with a new number. |
| B2 | PARKED or FAILED waves do not reserve their articles; the sensor reopens a wave on the same articles all night. | `store.py:16` lacks PARKED in `ACTIVE_WAVE_STATUSES`; `article_pack.load_candidates` does not exclude them [checked] | Table `ops_wave_articles` reserves articles until DONE or CANCELLED; regression test. |
| B3 | No Job Object; child `article_run`/`agy` survive a dead daemon; DBOS replays `analyze` or `--repair` and doubles token spend. | `procrun.py:119` `Popen(..., creationflags=CREATE_NO_WINDOW)` [checked] | `KILL_ON_JOB_CLOSE`, skip batches with valid output, `.inflight` file with PID, chaos test. |
| B4 | Poison-article loop: an article that never passes DoD stays pending; age rule T2 uses `fetched_at` and fires again at once. | `sensor.py:160`, `daemon.py:264-291` | Per-article attempt counter; after N attempts move to the Article Lane dead letter. |
| B5 | Bot token leaks through error messages into `ops_events`, JSONL, `/log` and sentinel context sent to Google. | `notify.py:33` puts the token in the URL [checked]; `notify.py:132`, `sentinel.py` | One `redact()` before every event, log or prompt write; test with a fake token. |
| B6 | `--finish` can be killed mid-ingest; `token_ledger` uses plain `INSERT`, so reruns duplicate rows. | `wave_flow.py:165-168,362` | Stop only at step boundaries; ledger upsert on (wave, batch). |
| B7 | A step exception leaves DBOS in ERROR while `ops_waves` stays ACTIVE; the sensor blocks forever with a green heartbeat. | `daemon.py:104-122` reconciles only at start | One source of truth for wave state; reconcile every sensor tick; red alert past the total deadline. |

- Non-code blockers: D-Telegram (R1) needs written confirmation before two-way P4. D8 (policy on sending full article text to Google and OpenRouter) was not asked by the plan.

### Severe findings (summary)

- A4: Task Scheduler "restart on failure" does not restart a crashed process; a 3-day limit and battery stop also kill the daemon. Fix: 2-minute repeat trigger, `IgnoreNew`, `ExecutionTimeLimit=PT0S`.
- A6, R13: wave work folders sit in OneDrive; locked files are saved as `…_HHMMSS.json`, which misses the `*.output.json` glob, so `--repair` re-spends tokens. Move them to `C:\data\news-scape\`.
- A8: `PipelineLock` is not atomic and manual `article_run.py` ignores it. C12: `probe_write` takes the `monocle.db` write lock every 60 s.
- H4, H5: the approval gate holds wave WIP, so a 2-hour meeting stalls the pipeline. Estimate 25-35 messages per day at L1, against the Google SRE norm of under 2 actionable incidents per shift.
- H6, H7, G6: "clean" counted a 0-article wave; `/reject` did not reset the streak; the plan said "5 days at L2" while code counted 5 waves.
- G4: `wave.auto_resume` forced at least L1 and spent tokens after the standing order expired (`daemon.py:257-263, 358-360`).
- G5, R2, C11: `/level L3` created a 7-day order and cleared `fail_streak`; buttons had no nonce or expiry; Telegram setup whitelisted every chat that ever messaged the bot.
- H8-H11, R5, R7, G11: `/failover auto` skipped the promised pre-approval; the default OpenRouter model was a stealth model whose terms allow logging and training; `/diagnose` offered a [Run] button after free LLM text.
- C6: the runner diff set `max_tokens: 24000` (line 427) [checked]. A 50-article batch at about 900 tokens per article needs about 45K, so batches were truncated, against ADR-0010. `CACHED` was missing from `RUNNER_STATUS_MAP`.
- G12: a 5-article canary batch breaks "`--batch` is the only batching"; a canary must be a wave with `--limit 5`.
- G8: wave step order was hard-coded in `drive_wave` while `.agents/pipeline.yaml` still said DSH, `run_code`, `--batch 100`; two orchestration sources break rule 07.
- A9, C8: three diverging definitions of "pending article"; `lookback_days: 1` dropped backlog; a 0-article pack counted as FAILED. A11, S7: threshold T1 was 100 in the plan and 50 in ADR-0011.
- R9: a Defender exclusion for raw_html and auto-logon weaken a company machine. R4: `openrouter/.env` sits in company OneDrive; rotate the key; `secrets/ops.env` is plain text.

### Post-review check (11:10)

- ADR-0012 was created at 10:56, after the code (10:35) and the council verdict (10:52). It was marked accepted on "đồng ý thực thi toàn bộ kế hoạch" and did not absorb the council findings. B1 was downgraded to "ADR written after the fact".
- US-029 was confirmed blocked. The daemon ran at L0 with no token spend, but one sensor pass measured 262.6 s on a 2-minute cycle, and the probe locked `monocle.db` every 60 s.
- The Task Scheduler task restarted itself after 84 s with a 5-minute repeat trigger, `IgnoreNew` and `PT0S`, which absorbed A4.
- Telegram had 5 unsent alerts in the outbox (no token yet). morninger was still a manual process from 28/09, so root gap 1 of plan §1 stayed open.
- 10,944 articles were outside the automatic scope (the report said 5,908). The implementation report listed B2, B3, B5, B6, B7 and omitted B1 and B4.
- Process lessons:
  - Review only a committed SHA, with implementation paused. Order MUST be approval, ADR, council on the ADR, code.
  - Each blocker needs a regression test named by its id. "Measure only" still loads the operational DB.

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| A. Accept the plan and code as written, with the per-wave L1 approval gate | Fastest path to autonomy | Seven blockers stay open; the gate contradicts the ADR-0008 amendment; token re-spend paths remain |
| B. Freeze code, write a new ADR, fix B1-B7, minimal P1, drop the per-wave gate (council roadmap S0-S4) | Removes re-spend and stuck-wave failures; human reviews where content exists | Slower; DBOS versus lease left to a chaos-criteria spike |
| C. Minimal only: Task Scheduler plus healthchecks.io, analysis in office hours, defer daemon, bot, TUI and sentinel | About 200 lines, 1.5-2 days | Leaves recovery to manual `--repair`; no autonomous waves |

- Council resolutions inside option B: DBOS is chosen only if it passes chaos cases B3, B6, B7 and replaces `ops_waves`; otherwise a lease of about 80-120 lines.
- Human review moves to (a) a daily stratified sample of 5 articles and (b) preview before xlsx delivery until 10 clean review days.
- Capture runs 24/7; analysis runs in duty hours. `ops-sentinel` is deferred until after P3 and may only return action codes from a closed list.
- Cut until S4: Textual TUI, 15-command bot, separate outbox, canary batching, L3 auto-delivery, `auto` failover, auto-logon, Defender exclusion.

## Recommendation

- Option B. The direction is right, but B1-B7 cause token re-spend or stuck waves exactly when nobody watches.
- Roadmap:
  - S0: freeze the code and rotate the OpenRouter key. S1: new high-risk ADR.
  - S2: minimal runnable set; gate is a 48-hour run, alert within 10 minutes of shutdown, no doubled tokens after a mid-analyze kill.
  - S3: fix B2-B7 with fake-agy chaos tests and 2 weeks of incident data, plus the Bronze dead letter (1,427 and rising).
  - S4: decide on daemon, DBOS, bot, TUI and sentinel from measurements.
- Promotion to L1 MUST require every B1-B7 regression test to pass plus one successful manual agy wave.

## Outcome

- 2026-10-01, operator decisions:
  - D1': use Telegram (BotFather); check `from.id`, private chats only; healthchecks.io stays an independent channel.
  - D8: articles may go to every provider; packets carry only `i`, `t`, `p` with no watchlist, user, tier or path. Internal data (logs, config, watchlist, secrets) MUST NOT travel in a payload. Model names are pinned for quality.
  - D9: operate while the machine is on; drop auto-logon, sleep disabling and the Defender exclusion; pause healthchecks.io on sleep. B3 and B7 become prerequisites.
  - D10: when eligible (100 articles, age or time window) the agent runs the workflow without per-wave approval; DoD decides ingest.
  - D11: the DB is the single source of truth; delivery is per-user configuration in a separate process; L3 auto-delivery is dropped.
  - D12: keep the previous file and redeliver with a version mark. D13: a clean wave has more than 0 articles, DoD of at least 90%, entity drift under threshold, no severe sample error.
  - D14: fix B2-B7 on the current branch.
- Autonomy ladder after D10 and D11: L0 measures and reports; L1 runs whole waves including `--finish` under a standing order.
- 2026-10-01 execution: B2-B7 and R2 fixed (`ops_wave_articles`, Job Object created suspended, `ops_article_attempts` with at most 2 attempts, `src/ops/redact.py`, boundary-only stop, reconcile every tick).
- Live-run fixes: task priority 7 slowed the sensor 30-300 times; `agy` was missing from the task PATH; batch results read stale logs. 611 tests passed (1 real-DB test skipped); real wave W10011351 finished DONE with 100/100 articles.
- Left open for the operator: Telegram token, L1 standing order, old backlog of 10,944 articles, per-user delivery, OpenRouter `max_tokens`.
- Linked: ADR-0012 (ops daemon), ADR-0014 (control room and Telegram role change), stories US-029 and US-031.
