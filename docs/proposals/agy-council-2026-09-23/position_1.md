# Position 1: Python runs the pipeline, agy is only a stateless function
Debater 1. Evidence: `spike1/RESULTS.md` (8 real agy 1.2.9 calls, 2026-09-23).

## 1. Thesis
agy plugs into the lane's one LLM seam as a **pure function**, `f(CORE, packet) -> {"r":[records]}`. Python owns batching, timing, validation, file writes, retries and the ledger. agy never sees the repo, never touches a file, and never decides what runs next. The one agy-native feature I tested (custom agents) failed silently, which argues for a minimal agy surface.

## 2. Architecture
```
Task Scheduler (07:30,12:30,16:30; IgnoreNew; ExecutionTimeLimit 90m)
   │  run_article_lane.ps1  (lock file + KILL_SWITCH check)
   ▼
article_run.py --wave auto --runner agy          ← Python owns all state
   ├─ prepare  (unchanged: article_pack → task.json/map.json, --batch 50)
   ├─ agy_runner.run_wave(manifest)  pool=2, one fresh process per batch
   │     for batch:
   │       msg = CORE_bytes + "\n\n## Packet\n\n" + task.json + RUNNER_TAIL
   │       Popen(agy …, cwd=%LOCALAPPDATA%\news-scape\agy_work\<wave>\,   (empty, no .agents,
   │             stdin=1 NDJSON line, encoding=utf-8, Job Object)         outside repo/OneDrive)
   │       parse stream → classify → validate(records vs packet)
   │       safe_atomic_write OUT_DIR/<batch>.output.json  (JSON array text)
   │       safe_atomic_write OUT_DIR/<batch>.meta.json    (provenance+usage)
   ├─ finish   (unchanged: article_expand → l1_ingest → agent_ingest → handoff)
   └─ token_ledger append --source agy (reads *.meta.json)
```
The output file stays a JSON array, which `article_expand.salvage_records` already parses, so the file-keyed `--finish`, `--repair` and `--resume` work unchanged. In the spike, 15 of 15 agy records passed `build_gold_output`.

## 3. Exact invocation (verified in c7/c8)
```
agy -p= --input-format stream-json --output-format stream-json
    --model gemini-3.8-flash-low --json-schema <work>\article_r.schema.json
    --print-timeout 300s --disable-slash-commands
stdin: {"event":"user","message":{"content":"<CORE><packet><RUNNER_TAIL>"}}\n
```
- **Stdin stream-json** gets around the 32K argv cap. The Vietnamese text came through intact.
- **The schema must be an object.** A top-level array fails with 400 and exit 3 (c1), because agy compiles the schema into a `finish` function declaration. `prefixItems` is also rejected. So the schema is `{"r":[{i,e:[[str,str]],s,k≤4,im≥40,sn∈3,ts∈5,c:[int]}]}`, and the wrapper unwraps `r`.
- **RUNNER_TAIL** goes after the packet ("submit once via structured output, don't print first, call no tools"). Without it, CORE's "reply with an array" instruction makes the model generate the answer twice. That cost 57.9k in and 4.1k out (c2), against 24.9k in and 2.1k out with the tail (c7). The CORE bytes stay byte-identical, so the existing prefix hash check still holds.
- **No `--agent`.** Spike S2 failed on all three variants. The log says `Agent "article-processor" not found, falling back to default`, yet the `init` event still reports the agent and the exit code is 0. I dropped the custom-agent idea until someone reproduces it with a global `~/.gemini/config/agents` entry, under its own ADR.
- **No `--dangerously-skip-permissions`** (ADR 0008 §2.2). Any tool call is denied, and the classifier treats a denial as a violation.
- `agy --version` is checked against a pinned value in `config/runtime.yaml` before the wave starts (ADR 0008 §2.6). The spike showed why: agy moved from 1.2.7 to 1.2.9 in two days. If the version drifts, the wave stops (FATAL) until an operator re-pins it.

## 4. Wrapper failure classifier
Checks run in order. Every outcome goes into `llm_trace` (harness.db) and `<batch>.meta.json`.

| Class | Detection | Action |
|---|---|---|
| FATAL | agy missing or version drift; exit 1/2; exit 3 with `retryable:false` (e.g. schema 400) | stop wave, exit≠0, alert (§2.4) |
| RETRYABLE | exit 3 with `retryable:true`; stderr 429/5xx | full-jitter backoff, max 3 tries, then POISON |
| QUOTA | the 429 persists after retries, or quota text | stop wave cleanly, alert; the next trigger resumes (`--resume`) |
| TIMEOUT | stderr "print timeout", or usage all zeros, or wall > 1.5×print-timeout | kill the Job Object, re-split into halves once |
| VIOLATION | exit 0 but `denied_actions` non-empty, OR any `step_type=="tool"` other than `finish`, OR more than one `agent_response` step (double generation), OR no `structured_output` | discard, retry once in a fresh process, then POISON |
| PARTIAL | output validates, but some `i` are missing, an `e[1]` is outside the 11 codes (15% of c7 entities leaked canonical IDs), an `IND` is non-canonical, or `c` is out of range | drop only the bad fields or records; the existing `--repair` repacks missing `i` |
| OK | all `i` present, order ok | atomic write |

The wave-level gate stays as it is: if more than 10% of records fail parsing, the wave stops before the DB load.

## 5. Triggers
- **Task Scheduler** runs three slots after the scrape windows. Settings: IgnoreNew, StartWhenAvailable, and an execution time limit. The action is `pwsh run_article_lane.ps1`, which takes a `.article.lock`, exits if `KILL_SWITCH` exists, and then runs a single chained Python command. Each stage runs only if the previous one exited 0. That chain is a plain DAG, with no watchdog on OneDrive, no daemon and no sidecar.
- **ADR 0008 amendment ("no path starts itself").** ADR 0010 has to say this openly. Registering the scheduled task *is* the operator's explicit command, and it is recorded with who, when and the slot list. It is revocable through `KILL_SWITCH` or by disabling the task. Wave size is capped by `--limit`. Manual `article_run.py --runner agy` stays available.

## 6. Governance fit
- **Rule 01 §1 (zero-tool, single-turn, prompt-in/JSON-out).** The payload is in the prompt and the output is JSON. Exactly one user turn goes in, and there is exactly one model call when the tail is used (c7/c8). The model has no file I/O: cwd is an empty directory, and Python does every read and write. **What I can't claim honestly:** agy still exposes 57 tools, and I could not disable them without `--agent`. "Zero-tool" becomes "zero tools *used*, enforced by detection plus denial", not "zero tools *offered*". ADR 0010 has to accept that gap or block the runner.
- **ADR 0008 §2.2/2.4/2.6.** No skip-permissions flag; the classifier fails loudly (§2.4 held in full, exit codes propagate); version is pinned and checked before the run.
- **Q1 (worker = in-process subagent, not headless).** This design contradicts Q1 directly, so ADR 0010 must supersede Q1 for `--runner agy` only. DSH stays the default runner.
- **Rule 03.** `safe_atomic_write` for output and meta files; the only DB writes are the ledger and `llm_trace`, each under `BEGIN IMMEDIATE` with `busy_timeout 30000`; `subprocess(encoding="utf-8", errors="replace")`; `agy_runner` gets added to `AUTOMATION_CLIS`. The agy work directory sits under `%LOCALAPPDATA%`, never OneDrive.
- **Provenance and token_ledger.** `article_expand.py:53-54` stops hardcoding provider and model. It reads `<batch>.meta.json` (`agent_provider=agy`, `model_used`, `agy_version`, `conversation_id`, `schema_sha`, `core_sha`) and falls back to dsh/deepseek-flash when that file is absent. `token_ledger append --source agy` sums the usage fields from the meta files, with `cache_read` recorded as observed.

## 7. Batch size from token math
Measured and derived: fixed cost ≈ 19.5k tokens per call (11.7k agy system + about 7.5k CORE + tail/schema); input ≈ 1.45k tokens per article; output ≈ 0.4k tokens per article. Cache is **not** budgeted: it hit only on exact repeats (c5/c6) and missed on the realistic shared-prefix case (c8).

| N/batch | tokens/call | fixed share | calls per 1,000 art | total/1,000 art |
|---|---|---|---|---|
| 25 | ~66k | 30% | 40 | ~2.63M |
| **50** | ~112k | 17% | 20 | **~2.24M** |
| 100 | ~205k (40k out) | 10% | 10 | ~2.05M |

**Recommendation: N=50.** Going to 100 saves only 8% but doubles the blast radius of a schema retry (agy re-emits the whole output) and pushes output to about 40k tokens per call, which invites TIMEOUT and #902-style cancellations. At 9–17s of model time per 5 articles, 50 articles should take about 90–150s, so I would set `--print-timeout` to 300s.

## 8. Known weaknesses (honest)
1. **About 12k tokens of agy scaffolding per call, which I could not remove.** S2 failed, so roughly 17% of spend is agy's own system prompt at N=50. A DSH-style prefix cache does not work here.
2. **Zero-tool is enforced after the fact, not by construction.** The global `permissions.allow` includes `command(regex:.*\.py$)`. A tool-seeking model (c3/c4 tried `run_command`) could run an allowed script if cwd pointed at the repo. The isolated cwd is the real guard, and nothing verifies it beyond the spike.
3. **The schema cannot enforce `e` group codes by position**, so Python repair is required: 15% of codes were wrong in one run.
4. **Silent-failure surface.** agy reports success on denial, timeout and agent fallback. The classifier depends on stream heuristics, and those can break when agy self-updates. Version pinning helps, but agy.exe auto-updates itself, so the pin detects drift rather than preventing it.
5. **Quota is shared** with interactive and IDE use, and agy reports no cost field.
6. **Scheduling conflicts with the premise of the ADR 0008 amendment.** That needs explicit human approval (Tier 3), not an argument from me.
7. **Only 15 articles were quality-checked.** That is too few to say agy/Gemini matches DeepSeek quality. It needs an A/B run of about 200 articles on the same wave before `--runner agy` goes beyond draft.
