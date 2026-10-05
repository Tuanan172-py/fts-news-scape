# Rebuttal 2 (round 3): verdict on "D1 one-shot + D2 worker profile + custom agent + D3 ops shell"
Evidence: `spike2/RESULTS.md` § Joint spike (J1–J5).

## Verdict: adopt, with four changes
A **global-scope** custom agent inside the sandboxed worker profile loads. The log shows `agent=true` with no fallback, and the agent removes about 11.3k tokens of agy scaffolding per call:

| Packet | D1 baseline (schema+tail) | Agent, no schema/tail |
|---|---|---|
| B | 24,881 in / 2,096 out | **13,613 / 1,530** (−45%) |
| C | 26,382 / 1,905 | **15,119 / 1,403** (−43%) |

Both runs were single-turn and 5/5 in order, with 0 invalid group codes (c7 had 15%) and `c` in range. A run nudged to `view_file` made no tool step. Fixed cost falls to about 8k, so N=25 costs about 55k per call instead of 66k. **I'd move to N=25–30** for a smaller blast radius.

## What I would change
1. **Drop `--json-schema` and RUNNER_TAIL.**
   - `tools: []` removes agy's hidden `finish` tool, which `--json-schema` depends on.
   - Result: a 4-turn re-prompt loop, 2.4–3.6x the tokens, no `structured_output`, and a hidden `manage_task` call (J1, J5).
   - CORE's native "one JSON array" instruction works byte-identical. Python parses (`salvage_records`) and validates with jsonschema plus domain checks.
2. **Check agent loading from the log, not `init`.**
   - `init` claims the agent and 57 tools whether or not the agent loaded.
   - Treat it as FATAL when the per-run `cli.log` lacks `agent=true`, contains `not found, falling back`, or the first-call input exceeds CORE + packet + 3k.
3. **Regenerate and hash-check the profile every run.** agy rewrites `settings.json` in place.
   - Contents: the agent `.md` (frontmatter + CORE, recorded as `core_sha`), `settings.json` with no allow rules, and an optional PreToolUse deny-all hook. Hooks fire in `-p` and cost nothing unless a tool is attempted.
   - Pin the agy version (1.2.7 → 1.2.9 in days).
   - The `HOME`/`ANTIGRAVITY_APP_DATA_DIR` override is undocumented. D3's per-tick canary must assert the log line.
4. **Keep VIOLATION = any tool step.** `manage_task` still ran in J1 and J5. ADR 0010 can honestly say "zero tools offered by agent definition, zero used by detection."

D3's ops shell is unchanged. One note: auth comes from the Windows keyring, so the profile shares the user's account and quota. Logged-off runs are still impossible.

## Is an MCP repair lane still worth drafting?
**No. I withdraw it.**
- Repair is another one-shot `--repair` call at about 8k fixed cost.
- Invalid codes were 0 in both agent runs.
- MCP needs `call_mcp_tool`, which reopens the Rule 01 §1 exception.
- Cache was 0 across processes even with a near-identical prefix (J3→J4), so multi-turn never amortises.

Reopen it only if L0 telemetry shows #902/#1077 batch losses above 5%.
