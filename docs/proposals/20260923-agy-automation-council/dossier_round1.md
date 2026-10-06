# Council dossier — Round 1 findings (agy automation for News-Scape)
Date 2026-09-23. Repo: C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape (read-only for debaters).
Raw probe files: C:\Users\anpt\AppData\Local\Temp\claude\C--Users-anpt\ad7d926f-4ea6-4acb-a36f-dc4d6006a9aa\scratchpad\agy_probe\

## A. agy 1.2.7 ground truth (VERIFIED-LOCAL unless noted)
- agy.exe is a native Go exe (~203MB), self-updating (agy.exe.*.old files present) → pin/record version.
- `agy -p "OK" --output-format json` → envelope {conversation_id,status,response,duration_seconds,num_turns,usage{input_tokens,output_tokens,thinking_tokens,cache_read_tokens,total_tokens}}. ~11.7k input tokens fixed system-prompt overhead per call; process startup 6–9s; cache_read_tokens = 0 in ALL tests (incl. multi-turn). No cost field.
- **Text-mode stdin is IGNORED** by `-p` (prompt replied NOSTDIN). `-p -` = literal "-".
- **`-p= --input-format stream-json --output-format stream-json`** works: NDJSON `{"event":"user","message":{"content":"..."}}` per turn, one `result` event per turn, shared conversation_id, Vietnamese UTF-8 intact. Invalid line → exit 1. Events: init (lists ~55 tools, permission_mode request-review), step_update, result (usage cumulative).
- `--json-schema file` works: agent self-corrects on schema violation (retry doubled tokens). Parse ONLY `structured_output`; `response` contains junk attempts. Applies to final result only in stream-json.
- Silent failures (exit 0 + status SUCCESS): permission-denied tool (response "", no structured_output, `denied_actions` non-empty); `--print-timeout` expiry (usage zeros, stderr "print timeout ... returning partial output").
- Exit 1 invalid model/input, exit 2 usage error, exit 3 + stderr `AGY_ERROR:{..retryable..}` API failures (changelog; not observed). In-process retry on 429/5xx.
- Default --print-timeout now unlimited (docs say 5m, stale) → always pass explicitly.
- 3 parallel agy -p processes OK. `--conversation <id>` resumes (uses default model unless --model pinned). Avoid --continue (races).
- Models: gemini-3.8-flash-{low,medium,high}, 3.7/3.6 flash, gemini-3.1-pro-{high,low}, claude-sonnet-4-6, claude-opus-4-6-thinking, gpt-oss-120b-medium.
- Quota: shared "Work Done" pool with IDE/interactive use, 5h refresh (Pro/Ultra) + weekly caps (SOURCED antigravity.google/docs/plans).
- Open bugs: #794 json-schema + denied tool → exit0 no structured_output; #902 ~10% long tool-heavy stream-json runs CANCELED/empty; #1044 run_command killed at turn end; #1077 invoke_subagent output lost.
- Settings: ~/.gemini/antigravity-cli/settings.json has broad permissions.allow and trustedWorkspaces incl. project folder; `artifactReviewPolicy: always-proceed`.
- `agy models/agents --output-format json` rejected despite changelog; `/quota` in -p went to model.

## B. agy-native features (Researcher D)
- Custom agents: `.agents/agents/<name>.md` (workspace) or ~/.gemini/config/agents/; frontmatter name, description, tools, model, commandExecutionPolicy(off/auto/eager/sandbox), mcpServers, skills, rules, inheritCustomizations, excludeDefaultComponents:true (drops default prompt sections & builtin tools → could cut the 11.7k overhead + stabilize prefix; UNVERIFIED). NOTE: repo already has `.agents/` (rules, skills, dsh, registry.yaml) → agy will auto-load the repo's `.agents/rules` & skills when cwd is inside repo (20k-token rules budget) — risk of token bloat & nondeterminism.
- Hooks (hooks.json in .agents/ or ~/.gemini/config or plugin): PreToolUse/PostToolUse (matcher, allow/deny/ask/overwrite), PreInvocation(injectSteps), PostInvocation, Stop(decision continue). Command-only, cmd /c, JSON stdin/stdout, 30s. Firing in -p mode UNVERIFIED.
- MCP: `agy mcp add newsq python -m ...` or per-agent `mcpServers`. Pattern "pull-worker": agent calls claim_batch/get_article/submit_result (Python validates → SQLite txn). Undeclared args rejected; headless waits for MCP load.
- Plugins bundle agent+hooks+mcp+skills (agy plugin install/validate). `--disable-slash-commands` to avoid article text starting with "/" being expanded.
- Sidecars (~/.gemini/config/sidecars/<n>/sidecar.json, builtin "schedule" cron, restart_policy) + hidden `agy agentapi new-conversation|send-message|get-conversation-metadata` (needs projectId). Requires Antigravity app/daemon host? UNVERIFIED. No json-schema. Fire-and-forget.
- remote-control: human remote UI only; NOT a programmatic trigger.

## C. Windows / trigger mechanics (Researcher C)
- CreateProcessW limit verified: 32,000 ok, 32,800 → WinError 206; cmd.exe 8,191.
- Python 3.13 Anaconda utf8_mode=0, preferred encoding cp1252 → must set encoding="utf-8" on pipes / PYTHONUTF8=1.
- psutil, watchdog, jsonschema installed.
- **monocle.db (+WAL) lives in OneDrive**; data/archive_conflicts has per-machine conflict copies → OneDrive sync conflicts already happening. Any DB-as-queue must be local (or accept risk).
- Trigger comparison: Task Scheduler (IgnoreNew, StartWhenAvailable, DisallowStartIfOnBatteries=false, ExecutionTimeLimit) high robustness; APScheduler daemon medium; watchdog on OneDrive folder LOW (dup events, placeholders); SQLite job table + leases highest; chained DAG (plain Python/doit) good for batch; Prefect/Dagster too heavy.
- Kill process tree: Job Object KILL_ON_JOB_CLOSE or psutil children; CREATE_NEW_PROCESS_GROUP insufficient.
- Proposed failure classifier: OK / SOFT_FAIL / RETRYABLE / FATAL / TIMEOUT / UNKNOWN; bounded pool 2–3; full-jitter backoff; poison after 3; llm_trace table; Teams webhook alert.

## D. Repo & governance (Researcher B, file:line refs)
- Only ONE LLM stage in article lane: `article_analyze`. Everything else deterministic. Today: `article_run.py --wave W` (prepare) → writes `data/agent_tasks/article/article_<wave>_NN.task.json` ({"d","n","a":[{"i","t","p":[]}]}, indent=1, 100 art/batch, ~348KB/packet) + `.map.json` + `wave_<W>.conductor.ts`; HUMAN pastes .ts into DSH GUI run_code; DSH conductor calls subagent `agent_article` (deepseek-flash, reasoning off, toolFilter allow [], one-shot) per batch in parallel after a cache-warm call; writes raw text to `data/agent_outputs_article/<batch>.output.json`; then `article_run.py --finish` (article_expand → l1_ingest → agent_ingest → token_ledger → handoff) ; `--repair` repacks missing i's; `--resume` file-based. parse-fail >10% stops wave before DB load. Delivery (write_user_output → xlsx) is separate/manual.
- Prefix: `build_article_prefix.py` → `project/data/prefix/ARTICLE_SYSTEM_CORE.md` (~6,343 tok, hash-checked) pasted byte-identical into DSH persona for DeepSeek auto prefix cache.
- Scrape: `python -m src.morninger` APScheduler (capture 15m, derive 30m) started manually + news_cron 16:00 run_once.py (collide, OPEN-ITEMS A0-5). `run_daily.ps1` has `.pipeline.lock` single-instance lock (legacy lane). No trigger exists for article lane.
- `auto_pilot.py` is a legacy working agy runner (`agy -p <prompt> --effort low`) whose prompt tells agent to read packet file & write output → violates Rule 01 §1.
- Governance: AGENTS.md §0 → new runner = Tier 3 HIGH-RISK (Hard Gate → ADR → human approval → Detailed Trace), precedent ADR 0009. Next ADR = 0010. ADR 0009 §2.7: agy kept as alternative runner, must pass ADR 0008. ADR 0008 §2.4 "fail loud" in force; §2.2 (no --dangerously-skip-permissions default) and §2.6 (pin version, check exists) revive for agy; ADR 0008 amendment makes an explicit operator command the approval — "no path starts itself" → event-triggered unattended run must be addressed explicitly. WIP=1 (no story in_progress now). Rule 07 §4 five-step checklist (registry, SKILL, pipeline stage, story+proof, KPIs) else status draft; taxonomy operator/cognitive/conductor. **Rule 01 §1: zero-tool, single-turn, prompt-in/JSON-out; plan §5 invariant: LLM does not read/write files.** Rule 03: safe_atomic_write, single-writer DB BEGIN IMMEDIATE, busy_timeout 30000, subprocess encoding utf-8/errors replace, add CLI to AUTOMATION_CLIS test. **Q1 (plan 20260918-1651 :110): worker = subagent PTC in-process, NOT headless, NOT sdk** → agy headless contradicts Q1, needs ADR. SESSION-LATEST §37: "compact JSON" rule was wrong (DSH read tool line cap); agy has no such cap. ADR 0009 §2.3 model = deepseek-flash everywhere → Gemini = new provider flag. Provenance hardcoded AGENT_PROVIDER="dsh", MODEL_USED="deepseek-flash" (article_expand.py:53-54) must be parameterized. token_ledger only reads DSH sessions.
- Schema claims: missing `m` materiality VERIFIED (and downstream `_sort_key` reads nested materiality.score only — top-level fallback dead code; materiality not in xlsx columns) → adding m is a contract change (prefix hash, expander, maybe xlsx) = separate high-risk item, NOT required to ship runner. `e` = [surface, group] with 11 codes VERIFIED. `ts: arch→archive` VERIFIED.
- Seam: add `article_run.py --runner {dsh,agy}`: agy mode loops manifest batches, sends task.json content + ARTICLE_SYSTEM_CORE as input, writes stdout structured_output to OUT_DIR/<batch>.output.json; --finish/--repair/--resume unchanged (file-keyed).

## E. The user's prior draft (to be critiqued, not trusted)
Proposed Python conductor + agy worker, 25 art/batch, pass payload via stdin with `--input-format text` (NOW REFUTED: text stdin ignored), --dangerously-skip-permissions (conflicts ADR 0008 §2.2), model gemini-3.8-flash-low, compact JSON, add `m` field to schema, ADR 0010, spike, story US-024 (NOTE: US-024 id already used/implemented per harness.db).
