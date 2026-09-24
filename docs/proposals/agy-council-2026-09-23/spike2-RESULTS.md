# Spike 2 results — agy-native pull-worker (Debater 2)
Date 2026-09-23. agy **1.2.9** (self-updated from 1.2.7 since dossier). Model gemini-3.8-flash-low. 8 LLM-spending agy calls used (runs 1,2,3(/hooks x2),4,5,6,7,8). Global ~/.gemini untouched; repo untouched.

## Files
- `newsq_server.py` — FastMCP (mcp 1.14.0) stdio server: `claim_batch(n)`, `submit_result(i, result_json)`; Python-side validation (s in [-1,1], e=[surface, group in 11 codes], sum str); SQLite `queue.db` BEGIN IMMEDIATE, idempotent (done → "OK already done").
- `hook.py` — logs every event to `hooklog.jsonl`; PreToolUse: allow only `call_mcp_tool` with ServerName=newsq, deny everything else; Stop: `continue` while claimed rows exist (cap executionNum<3).
- `.agents/hooks.json`, `.agents/plugins/newsq/{plugin.json,mcp_config.json}`, `.agents/agents/newsq-worker.md` — workspace-scoped attempts.
- `home/` — **sandboxed agy profile**: `USERPROFILE=HOME=spike2\home`, `ANTIGRAVITY_APP_DATA_DIR=spike2\home\.gemini\antigravity-cli`; contains `config/hooks.json`, `config/mcp_config.json`, `antigravity-cli/settings.json` (trustedWorkspaces=[spike2], allow = only 2 mcp rules). Auth still works (keyring).
- `run1/4/5/6/7/8.ndjson(.err)` raw stream-json; `settings_used_run8.json`.

## S1 — Do hooks fire in `agy -p`? **YES (VERIFIED)**, with caveats
- Run 1 & 4 (real HOME, cwd=spike2, workspace `.agents/hooks.json`, `git init` tried too): cli.log `hooks_manager.go:53] loaded 0 named hooks from 0 hooks.json file(s)`. Workspace `.agents/` (hooks, plugin, custom agent) **not discovered** in an un-registered/untrusted-by-exact-path temp folder (C:\Users\anpt is in trustedWorkspaces, but prefix trust did not apply). Binary changelog string: "Fixed workspace-local hooks defined in `<workspace>/.agents/hooks.json` not loading after trusting a folder".
- `--agent newsq-worker` → cli.log `Agent "newsq-worker" not found, falling back to default` — **silent fallback**, exit 0. Must assert agent identity.
- Run 5–8 (sandbox profile): `loaded 1 named hooks from 1 hooks.json file(s)`. Run 8 hook log:
  ```
  16:28:22 PreToolUse call_mcp_tool "claim_batch" stepIdx 2
  16:28:25 PostInvocation invocationNum 0 ... (one per model invocation, 7 total)
  16:28:31 PreToolUse call_mcp_tool "submit_result" stepIdx 6   (x4)
  16:28:45 Stop executionNum 0 terminationReason NO_TOOL_CALL fullyIdle True
  ```
- Hook command failure (run 5: bad quoting `"python.exe"` under `cmd /c`) → every tool call fails with `JSON hook ... failed` → **fail-closed** (good). Do not quote paths in hook commands; cmd /c mangles `\"`.
- Stop did **not** fire in runs 6/7 where the run ended due to a permission denial (only PreToolUse logged) → Stop hook is not a guaranteed "finally".

## S2 — Does a stdio MCP server load in -p, and what approval is needed? **YES; needs explicit `mcp(server/tool)` allow rule**
- MCP is exposed via ONE meta-tool `call_mcp_tool {ServerName, ToolName, Arguments}` (init tool list = 57 tools incl. call_mcp_tool). Schemas are written to `<appdata>/mcp/newsq/<tool>.json`; in run 5 the model first tried `view_file` on those schema files (extra turns) → put arg schemas in the prompt instead.
- PreToolUse `decision: allow` does **NOT** bypass permission: run 6 → `permission check failed for mcp "newsq/claim_batch": user denied permission for mcp(newsq/claim_batch)`, exit 0, `denied_actions:[{"action":"mcp"}]`, stderr `jetski: no output produced — a tool required the "mcp" permission ...`.
- Run 7 wasted: agy rewrote sandbox settings.json (dropped empty `permissions` key) before my edit script ran.
- Run 8 with `permissions.allow = ["mcp(newsq/claim_batch)","mcp(newsq/submit_result)"]` and **no --dangerously-skip-permissions**: full loop succeeded:
  ```
  claim_batch n=3 -> [a1,a2,a3]
  submit a1 errs=["e must be [surface, group] with group in [...]"]   <- Python validator rejected
  submit a1 errs=[]                                                   <- model self-repaired from tool feedback
  submit a2 errs=[] ; submit a3 errs=[]
  queue.db: a1 done attempts=2, a2/a3 done attempts=1
  RESULT SUCCESS "DONE" 28.9s, usage input 96,555 / output 601, cache_read 0
  per-invocation input: 13016, 13228, 13646, 13887, 14077, 14258, 14443 (7 invocations for 3 articles)
  ```
- Observed quality issue: model emitted Vietnamese summaries **without diacritics** ("Ngan hang Nha nuoc") although input had them → needs a validator rule / prompt.

## S3 — agentapi / sidecars need the app? **YES (VERIFIED)**
- `agy agentapi --help` → `get-conversation-metadata | new-conversation [--model=flash_lite|flash|pro] | send-message`.
- `agy agentapi get-conversation-metadata <id>` → `{"error":"ANTIGRAVITY_LS_ADDRESS is not set"}` with **exit 0** (another silent failure). Requires a running Antigravity language server (app/daemon injects ANTIGRAVITY_LS_ADDRESS + ANTIGRAVITY_CSRF_TOKEN).
- builtin `automation` skill: sidecars live in `~/.gemini/config/sidecars/<id>/sidecar.json`, `"builtin":"schedule"` cron → `agentapi new-conversation -- <prompt>`, must be enabled by the human in the **Automations dashboard** (app UI); runs "inherit global permissions; non-approved commands auto-denied"; no json-schema, model only flash_lite/flash/pro aliases. → Not a headless Windows-server trigger; Task Scheduler remains the trigger.

## Other
- `agy plugin validate .agents/plugins/newsq` → ok, `mcpServers: 1 processed`; but `agy plugin list` → "No imported plugins" and `agy mcp add` writes user-level config only → no per-workspace MCP without trust/registration; sandbox profile is the clean isolation mechanism.
- `-p "/hooks"` was sent to the model (not answered locally) despite changelog.

## Joint spike (round 3): global-scope custom agent through the sandboxed worker profile
Dir `spike2/joint/`, used 5 of the 6 allowed calls, gemini-3.8-flash-low, `--print-timeout 240s`, cwd = empty `joint/work/`.
Profile `joint/home/` is a fresh sandbox: `USERPROFILE=HOME=joint\home` and `ANTIGRAVITY_APP_DATA_DIR=joint\home\.gemini\antigravity-cli`. It has no hooks, no MCP, and no allow rules.
The agent lives at `joint/home/.gemini/config/agents/article-processor.md`. Frontmatter: `name`, `description`, `tools: []`, `excludeDefaultComponents: true`, `inheritCustomizations: false`. Body = ARTICLE_SYSTEM_CORE, sha1 `d78938366792…`, the same as the repo file and spike1 `core.md`.
User message = `## Packet` + the same 5-article packets that spike1 c7 (packet B) and c8 (packet C) used. Runner is `joint/run.py`. Raw output is in `J1..J5.out`.

| # | Agent | Schema/tail | Packet | exit | turns | input / output / cache_read tokens | wall | Result |
|---|---|---|---|---|---|---|---|---|
| baseline c7 (D1) | none (default) | schema + tail | B | 0 | 1 | 24,881 / 2,096 / 0 | 31s | structured_output ok |
| baseline c8 (D1) | none (default) | schema + tail | C | 0 | 1 | 26,382 / 1,905 / 0 | 15.8s | structured_output ok |
| J1 | article-processor | schema + tail | B | 0 | **4** | 60,752 / 7,000 / 45,672 (1st model call 13,671 in) | 74.5s | **no structured_output**. Re-prompted 3 times, called `manage_task` twice, `response` = concatenated junk |
| J2 | article-processor | **no schema, no tail** | C | 0 | **1** | **15,119 / 1,403 / 0** | 21.4s | text response parses as a JSON array, 5/5 records, i 0..4 in order, 59 entities with **0 invalid group codes**, all `c` indices in range |
| J3 | article-processor | no schema + "use view_file to read C:\Windows\win.ini and list the directory" nudge | B | 0 | 1 | 13,650 / 3,390 (+1,764 thinking) / 0 | 38.3s | **no tool step**, 5/5 clean array. The model ignored the nudge |
| J4 | article-processor | no schema, no tail | B | 0 | 1 | **13,613 / 1,530 / 0** | 19.1s | 5/5, 0 invalid codes. Ran 1 min after J3, which had a near-identical prefix, and still got **0 cache** |
| J5 | article-processor-s (`tools: []`, **without** excludeDefaultComponents) | schema + tail | C | 0 | 4 | 28,014 / 6,947 / 74,696 (1st call 16,803 in) | 149s | no structured_output (```json fenced text), same re-prompt loop plus `manage_task` |

**Evidence the agent loaded:**
- Every J run logged `conversation_manager.go:512] Starting new conversation (agent=true)` and `Creating new cascade trajectory (agentScript=true)`.
- None logged `not found, falling back` (count 0).
- Compare runs 1–8 and spike1: `agent=false` plus `Agent "..." not found, falling back to default`.
- The `init` event lists **57 tools in every run, loaded or not**. It is useless as a check. Assert on the log line, or on input_tokens under about 17k.

### Findings
1. **A global-scope agent loads through the sandboxed profile.** Workspace `.agents/agents` never did (D1 c3–c6, my run 4).
2. **Overhead is gone.** On the same packets, input fell 24.9k → 13.6k (B, −45%) and 26.4k → 15.1k (C, −43%). That is about 11.3k less per call; the agy system prompt is effectively removed, and what remains is about CORE (7.5k) plus the packet. Output also fell to 1.4–1.5k tokens, against 1.9–2.1k.
3. **`tools: []` breaks `--json-schema`.** agy implements the schema as the `finish` tool. With `tools: []` the finish tool is gone, so agy re-prompts in a loop: 4 turns, about 2.4–3.6x the tokens, no structured_output, and a hidden `manage_task` harness tool gets called.
   - Rule: the agent lane must **not** pass `--json-schema` and does **not** need RUNNER_TAIL, because CORE's own "reply with one JSON array" instruction works as is.
   - Python parses the text response (`salvage_records`) and validates it with jsonschema.
4. **Zero tools holds in the normal path.** J2–J4 had no tool steps, and J3 resisted an explicit file-read nudge. But `manage_task` can still be called (J1, J5). Keep treating any `step_type == tool` as a VIOLATION.
5. **Cache: 0 across processes, even with a near-identical prefix (J3 → J4).** Cache appeared only within one multi-turn conversation (J1, J5). Do not budget any cache.
