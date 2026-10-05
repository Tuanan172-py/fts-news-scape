# Position 2: agy-native pull-worker (MCP + hooks + sandboxed profile)
Debater 2. Evidence: `spike2/RESULTS.md` (8 LLM calls, agy **1.2.9**, which self-updated from 1.2.7 during the council).

## 0. Verdict up front
I do **not** propose the MCP pull-worker as the main article lane. The spike shows it works end to end in headless mode without `--dangerously-skip-permissions`. It also shows that a loop with one article per turn costs about 30x more tokens (with cache_read=0) and breaks Rule 01 §1 on purpose. My proposal:
1. Two agy-native pieces go into the main lane whatever runner is chosen: a **sandboxed worker profile** and **hooks used as guardrails**.
2. A **coarse-grained MCP lane** is registered as a separate `draft` lane, first used for **repair** (re-running rejected or missing `i`s) and for evaluation. It is not the default until an ADR amends Rule 01 §1.

## 1. What the spike verified
| Question | Result |
|---|---|
| Workspace `.agents/` (hooks, plugin, custom agent) in a temp folder | **Not loaded**: log shows `loaded 0 named hooks from 0 hooks.json`. Trusting `C:\Users\anpt` did not carry down to the subfolder. `--agent newsq-worker` fell back to the default agent **silently** (exit 0). |
| Sandboxed profile (`USERPROFILE`/`HOME`/`ANTIGRAVITY_APP_DATA_DIR` → private dir) | Works. Auth still comes from the keyring. The profile loads only its own hooks.json, mcp_config.json, and a 2-rule allowlist. The user's broad global `command(regex:.*\.py$)` rules are **not** inherited. |
| Hooks in `-p` | **Fire.** PreToolUse runs once per tool call; PostInvocation runs once per model call (7 of them); Stop fired with `terminationReason NO_TOOL_CALL`. A crashing hook fails closed: every tool errors. |
| Stdio MCP in `-p` | Loads. Tools are reached through one meta-tool, `call_mcp_tool{ServerName,ToolName,Arguments}`. Schemas are written to disk, and the model tried `view_file` on them, so the prompt must carry the schemas. |
| Approval | A PreToolUse `allow` does **not** grant permission. You need `permissions.allow: ["mcp(newsq/claim_batch)","mcp(newsq/submit_result)"]`. Without it the run exits 0 with `denied_actions` (silent failure). |
| Self-repair | `submit a1 → REJECTED (bad group code) → resubmit OK`. a2 and a3 passed first try. queue.db: all `done`, attempts 2/1/1. |
| Stop hook | Did **not** fire when a run ended on a permission denial. It is not a `finally`. |
| agentapi / sidecars | `agentapi` returns `{"error":"ANTIGRAVITY_LS_ADDRESS is not set"}` with **exit 0**. Sidecars need the running Antigravity app, and a human has to enable each one in the Automations dashboard. **Rejected as a trigger.** Windows Task Scheduler stays the trigger. |
| Quality | The model left Vietnamese diacritics out of `sum` ("Ngan hang Nha nuoc"). The validator must check for this. |

## 2. Architecture (coarse MCP lane)
```
Task Scheduler (IgnoreNew, ExecutionTimeLimit)
   │
   ▼
article_run.py --runner agy-mcp --wave W          (Python conductor, Job Object kill-tree)
   │ prepare (unchanged) → task.json + map.json
   │ load items into LOCAL queue.db (%LOCALAPPDATA%, NOT OneDrive) with lease columns
   │ spawn N≤3:  agy -p <prompt> --model gemini-3.8-flash-low --print-timeout 600s
   │             --output-format stream-json --disable-slash-commands
   │             env USERPROFILE/HOME/ANTIGRAVITY_APP_DATA_DIR = worker_profile\
   ▼
┌──────────── agy (sandboxed worker profile) ────────────────────────────┐
│ settings.json: trustedWorkspaces=[lane dir], allow = mcp(newsq/*) ONLY │
│ hooks.json:                                                            │
│   PreToolUse(*)   → deny unless call_mcp_tool && ServerName==newsq     │
│   PostInvocation  → log usage/invocationNum → llm_trace; terminate     │
│                     once the lease holds no unsubmitted items          │
│   Stop            → continue (max 2) while leased items unsubmitted    │
│ mcp_config.json: newsq → python -m newsq_server                        │
└──────────────┬─────────────────────────────────────────────────────────┘
               │ call_mcp_tool
               ▼
newsq_server.py (deterministic Python, 0 tokens)
   claim_batch(k=25)    → BEGIN IMMEDIATE lease; returns compact {i,t,p[]}
   submit_batch(items)  → jsonschema + domain checks per item; idempotent upsert;
                          returns ONLY per-item errors → model repairs just those
   on lease complete    → safe_atomic_write data/agent_outputs_article/<batch>.output.json
   │
   ▼
article_run.py --finish  (unchanged: expand → l1_ingest → agent_ingest → ledger)
```
Components: `newsq_server.py`, `worker_profile/` (3 JSON files generated each run), `hook.py`, a conductor branch, and an `llm_trace` table. Because of the output-file seam, `--finish/--repair/--resume` stay unchanged.

## 3. Token and turn economics (measured, then extrapolated)
Run 8 covered 3 articles in 7 model invocations. Input tokens per invocation were 13,016 → 14,443, for **96,555 input tokens in total** (cache_read 0). Each extra turn re-sends about 13k of fixed overhead plus all prior tool I/O. That is the O(n²) growth Rule 01 §1 exists to prevent.

Per 25 articles (≈25k tokens of text):
| Mode | Model calls | Input tokens (est.) |
|---|---|---|
| One-shot pure function | 1 | ~38k |
| One item per turn (spike style) | ~27 | ~1.1M (**~30x**) |
| Coarse: claim → submit_batch → DONE | 3 | ~95k (2.5x) |
| Coarse + PostInvocation `terminate` after a clean submit (UNVERIFIED) | 2 | ~52k (1.4x) |
| Coarse + PreInvocation `injectSteps{toolCall: claim_batch}` (UNVERIFIED) | 1–2 | ~40k (≈1.05x) |

The one-item-per-turn design is dead, and I concede that. The coarse design pays roughly 1.05–2.5x the tokens. In return it gets per-item validation feedback inside the same session. The one-shot equivalent is `--json-schema`, which regenerates the **whole** output on any violation (the dossier measured doubled tokens) and only checks shape. Python checks domain rules too: enum codes, the `c` paragraph-index range, diacritics.

## 4. Reliability against the known bugs
- **#1077 (invoke_subagent output lost)** and **#902 (~10% CANCELED or empty)**: the one-shot lane loses the whole batch when stdout is lost. In the MCP lane the result is **persisted when submit_batch commits**, not in the final message. A CANCELED run keeps everything submitted so far, and the lease expires so the rest is reclaimed. This is the strongest argument for the lane. Caveat: #902 targets long tool-heavy runs, and this lane is tool-heavy by definition. It still has to be bounded (k=25, ≤4 invocations, `--print-timeout`).
- **#794 (json-schema + denied tool → exit 0, no structured_output)**: the lane does not use `--json-schema`. Success is read from **DB state**, never from exit code or stdout. The conductor treats `denied_actions`, the `jetski: no output produced` stderr, and zero usage as failures.
- **#1044 (run_command killed at turn end)**: no `run_command` is used. MCP writes are synchronous inside the call.
- Newly found silent failures that **both lanes** must guard: an unknown `--agent` falls back to the default, `agentapi` errors return exit 0, and agy **rewrites** settings.json (it dropped an empty `permissions` key). The profile must be regenerated and hash-checked before every run.

## 5. Governance reconciliation
- **Rule 01 §1** (zero-tool, single turn, no self-verification loops) and **Rule 01 §2** (the subagent does not modify SQLite): the lane breaks §1 by design. It keeps the intent of §2, because the LLM calls a narrow API and Python validates and writes, with no file or search tools (PreToolUse denies them). Plan §5, "LLM does not read/write files", holds **literally**: MCP calls are not file I/O, and the spike showed the hook blocking `view_file`. I do not claim this dissolves §1. It needs an explicit **ADR 0010 amendment**: "a cognitive worker MAY be granted only the deterministic pipeline MCP tools of a registered lane; still no file or search tools."
- **Q1** (worker = in-process PTC subagent, not headless) is broken by **any** agy runner, not only mine. That goes in ADR 0010 regardless.
- **ADR 0008 §2.2**: met without `--dangerously-skip-permissions`, through an exact 2-rule allowlist in a sandboxed profile. That is stricter than today's global settings. §2.6: pin the version and check it (1.2.7 → 1.2.9 during this council shows why). "No path starts itself": Task Scheduler runs an operator-authored command, and sidecars are rejected.
- **Rule 07**: register `article_analyze_mcp` as `status: draft` with class cognitive, and add a pipeline stage for the repair lane only. WIP=1 means it ships **after** the default runner story.

## 6. Honest weaknesses
1. The coarse lane still costs more tokens and quota than one-shot. The hook-trimming tricks are unverified.
2. It adds agy surface area: MCP meta-tool indirection, a Stop hook that does not always fire, trust quirks, and self-updates.
3. It depends on an undocumented `HOME`/`ANTIGRAVITY_APP_DATA_DIR` override, because workspace-scoped customization failed.
4. Multi-turn does not improve content quality: diacritics were still stripped. Only validation catches that.
5. It carves an exception out of a rule the team wrote because of O(n²) costs.

**Ask of the council:** use one-shot as the default runner. Adopt the sandboxed profile and the PreToolUse deny-all hook for **every** agy invocation. Approve a bounded spike (≤20 calls) of the coarse MCP lane as the **repair path**, with go/no-go set by measured tokens (≤1.5x one-shot) and the CANCELED-recovery rate.
