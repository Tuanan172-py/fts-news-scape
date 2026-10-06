# Rebuttal 1 (Debater 1)

## Adopt
- **D2 profile:** a private `USERPROFILE`/`HOME`/`ANTIGRAVITY_APP_DATA_DIR` under `%LOCALAPPDATA%`, with `allow=[]`, regenerated and hash-checked every tick. This fixes my global `.py`-allow weakness.
- **D2 PreToolUse deny hook**, with one caveat. `--json-schema` answers through a `finish` tool (my c1/c5), so the hook must allow `finish`, or it blocks every answer. Spike A checks this.
- **D2 diacritics check**, added to the Python validation.
- **D3 prerequisites:**
  - make `--finish` fail loudly (today it uses `check=False`)
  - a Python lock under `C:\data`
  - assert the DB path equals `MONOCLE_DB_PATH`
  - runner-stamped waves, and refuse to mix runners
  - a runner-keyed ledger
- **D3 operations:** the L0/L1/L2 ladder, the standing order, `AGY_STOP` checked per batch, a canary batch, a dead-man alert, and ToS/egress confirmed first. IDs: #25, US-025, ADR 0010.
- **Withdraw:** "custom agent with tools:[]" as a guard, and D3 should drop it too. Both spikes show a silent fallback.

## Disagree
1. **30-min tick.** One scheduler entry is fine, and an idle tick costs nothing. The catch is that dispatching on any backlog fragments the work, and each call carries about 19.5k fixed tokens. Dispatch only when backlog is 50 or more. At the E3 windows, flush whatever remains. Inside the tick, keep the chained prepare → analyze → finish.
2. **Standing order.** It should expire in 7 days or less. Its SHA goes into every wave's metadata, and creating or renewing it writes a harness trace.
3. **40% quota cap.** agy exposes neither the pool size nor cost, so 40% has no denominator. Use absolute caps from our own ledger, per rolling 5 hours and per day. Start at 3M tokens/day. A 429 opens the breaker until the next 5-hour boundary.
4. **Batch 50, not 100.** D3's per-article overhead figures assume 11.7k fixed tokens per call. The measured figure is about 19.5k, because CORE alone is about 7.5k. On that basis N=100 saves only 8%, puts about 40k output tokens in each call, and doubles the loss when a schema retry happens. Allow N=100 only if spike B shows no truncation.
5. **MCP repair lane.** Not needed. The existing one-shot `--repair` already covers it, and bug #902 hits tool-heavy runs.

## Revised invocation
```
env USERPROFILE=HOME=<profile>, ANTIGRAVITY_APP_DATA_DIR=<profile>\.gemini\antigravity-cli,
    MONOCLE_DB_PATH=C:\data\news-scape\monocle.db, PYTHONUTF8=1;  cwd=<agy_work>\<wave>\ (empty)
agy -p= --input-format stream-json --output-format stream-json --model gemini-3.8-flash-low
    --json-schema schema_r.json --print-timeout 300s --disable-slash-commands
stdin: {"event":"user","message":{"content":CORE+packet+RUNNER_TAIL}}
```

## Check order
**Per tick:**
1. AGY_STOP / standing order
2. lock
3. DB path
4. agy version equals the pin
5. profile/hook hashes
6. CORE hash
7. quota caps / breaker
8. canary

**Per call:**
- a. exit code / AGY_ERROR → FATAL, RETRYABLE or QUOTA
- b. timeout or zero usage → TIMEOUT: kill the job, halve the batch
- c. `init.model` equals the pin
- d. a non-`finish` tool, or `denied_actions` → VIOLATION plus an alert; 2 in one wave stops it
- e. more than one `agent_response` → warn
- f. `structured_output.r` present
- g. domain checks (i coverage, 11 codes, IND, c range, im≥40, diacritics) → PARTIAL, then repair
- h. atomic write of output and meta
- i. ledger row

## Minimum before L1
- **Spike A (3 calls):** profile + hook + schema. Does `finish` pass the hook, and what is the overhead?
- **Spike B (2 calls):** real batches of N=50 and N=100.
- **Tests:** fake-agy fixtures for every failure class, plus lock and DB-path tests.
- **A/B:** about 200 articles, agy vs DSH. Gates:
  - parse_fail <2%
  - DoD ≥99% after repair
  - invalid codes <5%
  - BOTH-rate at most 5 points below DSH
  - tokens within ±20% of the model
  - a 20-article blind review
- Then 3 clean L0 waves.
