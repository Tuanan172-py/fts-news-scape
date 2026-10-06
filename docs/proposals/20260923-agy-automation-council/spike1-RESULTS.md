# Spike 1 results — Debater 1 (pure-function Python conductor)
Date 2026-09-23 16:20–16:32. agy **1.2.9** (dossier said 1.2.7 → self-updated within days). 8/8 agy calls used.
cwd for all calls: this dir (outside repo). Harness: `run.py` (subprocess, stdin=file, utf-8), analyser `an.py`.
Base command (every call):
```
agy -p= --input-format stream-json --output-format stream-json --model gemini-3.8-flash-low \
    --print-timeout 240s --disable-slash-commands [--agent article-processor] --json-schema <schema>
stdin: one NDJSON line {"event":"user","message":{"content": ...}}
```
Packets: articles [0:5], [5:10], [10:15] of `project/data/agent_tasks/article/article_W365_01.task.json`, re-indexed i=0..4, same {"d","n","a"} shape.

| # | Test | Input content | Schema | exit | status | in / out / cache tok | model wall | Result |
|---|---|---|---|---|---|---|---|---|
| c1 | S3 top-level array | CORE+packetA | `{"type":"array",...}` + `prefixItems` | **3** | ERROR | 0/0/0 | 7s | `INVALID_ARGUMENT 400: parameters.properties only allowed for OBJECT type ... items.items: missing field`; stderr `AGY_ERROR {"retryable":false,"error_code":400}` |
| c2 | S1 object wrapper | CORE+packetA | `{"r":[rec]}` e=array of string pairs | 0 | SUCCESS | 57,939 / 4,109 / 0 | 18.2s (28.5 wall) | 5/5 records, valid; **but 2 model calls**: model first printed the array as text (CORE says "reply with one JSON array"), then was re-prompted to call `finish` |
| c3 | S2 agent (flat `.agents/agents/article-processor.md`, tools:[], excludeDefaultComponents, inheritCustomizations:false, hidden) | packetA only | obj | 0 | SUCCESS | 20,837 / 501 / 0 | 3.6s | **agent not found → silent fallback to default agent**; model called `run_command dir` → denied; no structured_output; exit 0 |
| c4 | S2 agent (dir form `.agents/agents/article-processor/agent.md`, + mainAgent:true, subagent:false) | packetA only | obj | 0 | SUCCESS | 20,835 / 293 / 0 | 6.8s | same silent fallback + denied run_command |
| c5 | c4 after `git init` in spike dir | packetA only | obj | 0 | SUCCESS | 26,860 / 2,034 / **16,306** | 10.8s | still fallback; default agent produced **schema-valid garbage** (e = lists of 12 names, c = article index); `finish` rejected once (maxItems) then retried |
| c6 | minimal frontmatter (name, description, mainAgent, excludeDefaultComponents) | packetA only | obj | 0 | SUCCESS | 26,687 / 2,045 / **16,306** | 10.2s | still fallback; records out of order (1,0,3,4,2) |
| c7 | S1 + RUNNER TAIL appended after packet | CORE+packetB+tail | obj | 0 | SUCCESS | 24,881 / 2,096 / 0 | 17.0s (31 wall) | **single model call → finish**; 5/5 in order; 9/60 entity group codes invalid (`EXCHANGE`, `IND_GICS2:...`) |
| c8 | same as c7, packet C, 30s later | CORE+packetC+tail | obj | 0 | SUCCESS | 26,382 / 1,905 / 0 | 9.3s (15.8 wall) | single call; 5/5 in order; 0 bad codes |

Log evidence for S2 (`~/.gemini/antigravity-cli/log/cli-*.log`), every --agent run:
`W0923 16:22:12 session.go:91] Agent "article-processor" not found, falling back to default` — while the stream `init` event still reports `"agent":"article-processor"`. `init.tools` = 57 in all 8 runs.

Quality check (c2/c7/c8, via read-only import of `article_expand.build_gold_output`): 15/15 records produce valid gold output; `c` indices all in range; Vietnamese UTF-8 intact; non-IND surfaces not verbatim: 5 (c2), 0 (c7), 1 (c8).

## Findings
1. **S3: top-level array is rejected** (json-schema is compiled into a `finish` function declaration whose parameters must be an OBJECT). `prefixItems` (tuple typing) also rejected. Use `{"r":[...]}`; positional enum for `e[1]` cannot be expressed → Python must validate group codes (c7 leaked canonical IDs 15%).
2. **S1 works** with stream-json single turn; payload ~17–27K chars delivered fine via stdin (no argv limit). CORE's "answer with a text array" instruction conflicts with the finish tool and **doubles cost** (c2). A runner-specific tail placed AFTER the packet (CORE prefix bytes unchanged) fixes it: 1 model call, ~2.0k out per 5 articles.
3. **S2 failed**: workspace custom agents are not resolvable by `--agent` in `-p` mode here (3 frontmatter variants, 2 layouts, with/without git root). Global `~/.gemini/config/agents/` untested (forbidden). Overhead reduction (<11.7k) therefore **unverified**. The failure mode is dangerous: exit 0, init claims the agent, default agent (57 tools) runs.
4. **Cache**: `cache_read_tokens` 16,306 appeared only when the *entire* input was repeated within minutes (c5, c6); a shared ~19k prefix (system+CORE) with a different packet gave 0 (c8, 30s after c7). Treat cache as opportunistic, never budgeted.
5. **Token math** (derived): fixed per call ≈ 19.5k (≈11.7k agy system + ≈7.5k CORE + tail + finish-tool schema); packet ≈ 0.31 tok/char ≈ 1.45k tok/article average (full W365_01 = 429k chars/92 art); output ≈ 0.4k tok/article.
6. Default agent with bare data tries tools (`run_command dir`). Global settings `permissions.allow` contains e.g. `command(regex:.*\.py$)` → a tool-seeking agent in a repo cwd could auto-run pipeline scripts headless. Isolated cwd + tool-step detection are mandatory.
