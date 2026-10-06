---
id: ADR-0014
type: adr
title: Multi-agent supervision; ops_spans traces, control room, Telegram oversight, self-renewing mandate
status: accepted
lane: high-risk
created: 2026-10-01
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
approvers: [operator 2026-10-01]
story: [US-031]
amends: [ADR-0006, ADR-0012]
related: [ADR-0008, ADR-0010]
evidence:
  - commit:579163c
  - commit:0340f64
  - path:plans/20261001-1500-supervisor-control-room/plan.md
  - path:project/src/ops/trace.py
  - path:project/src/ops/control_room.py
  - path:project/src/ops/mandate.py
  - path:project/src/ops/improve.py
  - path:project/config/ops.yaml
  - test:project/tests/test_ops_trace.py
  - test:project/tests/test_ops_supervision.py
  - metric:agent_metrics table had zero rows before this ADR, 2026-10-01
  - operator:approved 2026-10-01 ("đồng ý thực thi toàn bộ quy trình, với các mục quyết định cần chốt đồng ý định hướng đề xuất"), decisions D-A to D-E
original: "commit:579163c"
reconstructed: 2026-10-06
summary: Adds runtime span traces in ops.db, a local read-only control room, a Telegram role change from approval to exception reporting, a 30-day conditionally self-renewing mandate replacing the 7-day standing order, and a deterministic improvement inbox.
summary_vi: Thêm vết ops_spans, Phòng điều khiển cục bộ, Telegram chỉ báo ngoại lệ, mandate 30 ngày tự gia hạn có điều kiện và hộp thư cải tiến tất định.
---

# ADR-0014 — Multi-agent supervision; ops_spans traces, control room, Telegram oversight, self-renewing mandate

## Context

- After ADR-0012 the system runs a whole wave by itself. The operator still cannot see how agents interact, which script each step runs, which tools it calls, what it costs and where it fails.
- The operator changed role: no more approving waves, only supervising and improving the process.
- Measured state on 2026-10-01:
  - `registry.yaml` already declares each agent's skill, entrypoint, I/O, allowed tools and KPIs. The gap is the runtime record.
  - Inside `article_run.py` each stage leaves only a log file.
  - `AgyRunner` reads `tool_invoked` and `denied_actions` but drops them after classifying errors.
  - The `agent_metrics` table has no rows.
- The design is `plans/20261001-1500-supervisor-control-room/plan.md`. Observation parts (P0 to P3) are lane normal; the self-renewing delegation (P4) is high-risk and needs this ADR.

## Decision

- D1. Two data layers.
  - A static map from `registry.yaml` and `pipeline.yaml`: who exists, class, skill, reads and writes, allowed tools.
  - Runtime traces in table `ops_spans` of `ops.db`. A wave is a span tree: `workflow` → `step` → `script`, `agent`, `gate`. `trace_id` is the wave code; `actor_id` matches the registry id.
  - Span attributes include model, tokens, latency, `tool_invoked`, `denied_actions`, `prefix_hash` and attempt count. Fields are OpenTelemetry-compatible, so a later push to Phoenix or Langfuse needs no change to span code (D-C).
  - Span code (`src/ops/trace.py`) MUST do nothing when `OPS_TRACE_DB`, `OPS_TRACE_WAVE` or `OPS_TRACE_PARENT` is missing. A manual `article_run.py` writes nothing and behaves the same. Every trace-write error is swallowed: a broken trace never breaks a wave.
  - Span ids are fixed by (wave, attempt, step), so a workflow rerun after a crash overwrites instead of duplicating.
  - Span points: each step in `wave_flow`; each stage in `article_run.py` (pack, expand, L1 ingest, Gold ingest, post-check, ledger, handoff); each batch in `AgyRunner`. Only `AgyRunner` is instrumented; the OpenRouter runner and the OpenCode adapter are not yet.
  - Per-agent KPIs are written to `agent_metrics` in `harness.db` when a wave settles, derived from traces. When `resolve_paths` receives an explicit folder (tests), KPIs go there and never touch the real `harness.db`.
- D2. Control room. An HTTP server inside the daemon (`ThreadingHTTPServer`, no new library), listening only on `127.0.0.1` (D-B: no remote access yet). Five screens: Overview, Waves, Agents, Incidents, Improvements.
  - It accepts only requests whose `Host` header is a local address (DNS-rebinding defence).
  - The only write action is deciding an improvement proposal. It needs a pass token generated at each start and embedded by the page.
  - The server disables `SO_REUSEADDR`, because on Windows it lets two processes bind one port, unlike Linux. If the port is taken, the control room is skipped and the daemon keeps running.
  - Data is read only from `ops.db`; there is no second source of truth.
- D3. Telegram changes role.
  - Per-wave approval buttons end. A normal wave only enters the digest (`alerts.push_wave_info: false`); individual messages are sent only for exceptions.
  - Digests at 08:00 and 18:00 list each agent (spans, success rate, tokens, latency), anomalies and open proposals. An anomaly deviates more than 2 standard deviations from the last 7 days, with at least 5 waves (D-D).
  - New commands: `/map`, `/trace`, `/agent`, `/mandate`, `/improve`, `/prop`.
- D4. Conditionally self-renewing mandate (D-A). The 7-day standing order of ADR-0012 is replaced by a 30-day mandate. With under 7 days left and a healthy system, the daemon extends it by 30 days and records `mandate.renewed`. Health is checked every 10 minutes:
  1. no red-level event in 24 hours;
  2. clean-wave streak of at least 5;
  3. no failed-wave streak;
  4. no Zero-Tool violation in 7 days.

  If the conditions fail, renewal stops, the reason is reported and the mandate runs out to L0. Two things never change. A mandate never granted or already expired MUST NOT be re-granted automatically; that is a human action (`/level L1`). `/stop` always revokes. Privilege-raising commands still need a second confirmation (ADR-0012).

  This does not rebuild a human approval gate, in line with the ADR-0008 amendment. It replaces a time-based safety latch with a condition-based one, which is why it needs this ADR.
- D5. Improvement inbox (D-E). A new agent `improvement-proposer` (operator class, 0 tokens) scans traces and KPIs hourly with deterministic detectors.
  - Detectors: first pass missing articles and tokens spent in repair, prefix cache not reused, Zero-Tool violations, repeated breaker opens, articles out of attempts, rising dead-letter.
  - At most 5 new proposals per week. A proposal deferred or rejected is not raised again for 30 days. Invariant violations always rank first.
  - Proposals MUST NOT execute themselves. Only **Open story** calls `harness_cli intake` and `story add` (`US-IMP-nnn`, `planned`). Detectors only measure and produce no semantic content, so they do not emulate an agent.
- D6. Out of scope at decision time:
  - `harness-auditor` stays draft. The plan expected it, but it is an LLM agent and rule 07 requires activation evidence that does not exist. The deterministic operator generates proposals instead.
  - No remote access (D-B). Telegram `/map` and `/trace` cover quick viewing.
  - No Phoenix or Langfuse yet (D-C); compatibility only.
  - No mandate granted. The daemon stays at L0 until the operator types `/level L1` and confirms.
  - P0 acceptance with a real wave through the daemon did not exist at writing time. Traces were tested with fake processes and a fake `AgyRunner`. The first real wave after L1 is the missing evidence.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep the 7-day standing order with manual renewal (D-A) | Requires a human click every week while the operator role is now supervision only; the conditional mandate keeps the latch without rebuilding an approval gate (reconstructed from plan §7 D-A). |
| Arize Phoenix over OpenTelemetry instead of a home-made UI (D-C) | Data already lives in `ops.db`, no new infrastructure is needed, and the trace tree carries project columns (skill, entrypoint, DoD gate). Phoenix stays a later spike (reconstructed from plan §7 D-C). |
| Remote control room access from phones (D-B) | Needs an authenticated public tunnel under IT policy; a Telegram Mini App also needs a public HTTPS URL. Telegram `/map` and `/trace` suffice (reconstructed from plan §7 D-B). |
| Activate the LLM `harness-auditor` to write proposals | Rule 07 requires activation evidence that does not exist; a deterministic operator measures without emulating an agent (D6). |

## Consequences

- Two extra `ops.db` writes per span; writes happen per step and per batch, not per article.
- The sensor no longer measures during a wave and never reads content columns, so supervision does not compete with the wave.
- The ingest gate, the token-recorded-only invariant and the "one wave, one program" rule do not change.
- Known risks from the plan: supervision slowing the system (target wave time increase at most 2%), and a false sense of control where quality is unmeasured; unmeasured metrics MUST show "not measured".

### Current status (2026-10-06)

- Implemented: `ops_spans`, the control room at `http://127.0.0.1:8787`, digests, the new commands, the mandate and the improvement inbox (`docs/OPEN-ITEMS.md` OPS-2).
- US-037 (session 2026-10-05) added spans for the OpenRouter runner and traced manual waves (`docs/SESSION-LATEST.md`).
- Still open: `harness-auditor` activation, remote access (D-B), a Phoenix spike (D-C) and a quality golden set.

## Rollback

- `control_room.enabled: false` in `config/ops.yaml` disables the control room.
- Removing or not setting the `OPS_TRACE_*` environment variables stops span writes.
- `alerts.push_wave_info: true` restores individual messages per wave.
- The mandate returns to a fixed term with `autonomy.renew_when_days_left: -1`.

## Follow-up

- [x] P0 to P4 implemented with US-031 (commit 579163c); closure gate and supervision fixes with commit 0340f64.
- [ ] P0 acceptance with a real wave through the daemon showing a full span tree.
- [ ] Span for the `opencode_native_run.py` adapter.
- [ ] `harness-auditor` to active after 10 correct diagnoses (rule 07).
- [ ] Quality golden set, so the control room can show correctness, not only coverage, latency and tokens.
