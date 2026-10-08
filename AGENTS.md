# AGENTS.md — Entrypoint and authority gate (news-scape)

> Read this first in every session, whatever the tool or model (Claude, Codex, agy, opencode, OpenRouter).
> This file is a stable shim; detail lives in the documents it cites by id.
> The app is what users touch. The harness is what agents touch.
> Harness language is English (ADR-0021.D4). Vietnamese appears only in quotes, code and delivered user output.

## 0. Rule one: classify every prompt into three tiers and close with the Harness Closure Table

| Tier | Scope | Flow |
|---|---|---|
| 1 TINY | Question, lookup, explanation, 1-2 line patch | No WIP block, answer or patch, minimal trace in `harness.db`, closure table |
| 2 NORMAL | Feature, refactor, deep research | Intake, bounded context, WIP=1, story `US-NNN`, proof test, standard trace, closure table |
| 3 HIGH-RISK | DB schema, data contract, API token, harness core | Intake, stop at the hard gate (`status: blocked`), ADR, human approval, detailed trace, closure table |

## 1. WIP = 1 per worktree

WIP=1 applies per git worktree (ADR-0022). In one worktree at most one story is `in_progress`, and it declares its `branch`. Agents on different worktrees work in parallel with equal, full authority over their own worktree. An urgent interruption inside a worktree parks that worktree's story first (`blocked` or `deferred`, with a reason).

## 2. Knowledge contract (ADR-0021)

- Read `docs/INDEX.md` first. It lists every governed document with id, status and one-line summary. Open a body only when its summary is relevant.
- Create ADRs, stories, proposals, plans, facts, rules, runs and runbooks only with `python scripts/harness_cli.py doc new --type <type> --title "<English title>"`. Never choose an id by hand.
- The contract is `docs/knowledge/README.md`; the schema is `docs/knowledge/schema.yaml`. `doc lint` runs in the pre-commit hook and blocks violations.
- Project memory is `docs/knowledge/facts/FACT-*.md`. Tool-private memory and plan folders (`~/.claude`, `~/.codex`, `.opencode`, `.kilo`) are scratch and never the only copy.
- Each invariant has one defining document. Cite its id (for example `ADR-0013.D1`); do not restate it.

## 3. Where product context lives (priority order)

Read these before inventing context; do not create a new knowledge folder.

0. `.agents/registry.yaml` and `.agents/pipeline.yaml`: source of truth for the agent network (who exists, operator/cognitive/conductor class, I/O boundaries, DoD, KPI) and the orchestration DAG. Daily operation: `.agents/dsh/RUNBOOK-article-lane.md`. Article Lane design: `plans/20260918-1651-article-lane-unified/plan.md`. Retirement of the L1/Gold lane: ADR-0010. Registry growth rules: `.agents/rules/07-agent-registry-governance.md`.
1. `.agents/skills/*`: operational and governance skills (`pipeline-radar`, `dsh-conductor` under `.agents/dsh/presets/news-scape-conductor/skills/`, `watchlist-curator`, `token-auditor`, `dod-gatekeeper`, `multi-agent-orchestrator-governance`, `l1-entity-matcher`). Draft specialist agents: `entity-curator`, `adversarial-dod-verifier`, `daily-brief-synthesizer`, `harness-auditor`. The skills `gold-financial-analyst` and `news-scape-agent-operations` describe the retired L1/Gold lane (ADR-0010) and are reference only.
2. `project/docs/skills/*`: per-source scraper knowledge (cafef, fireant, rss-sources, tnck).
3. `project/docs/{design,dev,domains,operations}/`: architecture, how-tos, source taxonomy, operations.
4. `project/docs/charter.md` and `project/docs/architecture.md`: goals, phases, TDRs.
5. `okf/`: cross-cutting operational knowledge.

## 4. Build and run (the product lives in `project/`)

The Python environment lives outside OneDrive at `C:\venvs\news-scape`. Never create a local `.venv`.

Cây mã vận hành nằm ở `C:\src\news-scraper`, ngoài OneDrive (ADR 0020). Dữ liệu ghi nằm dưới `MONOCLE_DATA_DIR` (mặc định `C:\data\news-scape`), đường dẫn do `project/src/core/paths.py` quyết định. Dữ liệu dùng chung xuất bản một chiều lên SharePoint qua `scripts/publish.py`, **chỉ vào sandbox `sites/FRA_DataIngestion/Shared Documents/AnPT`**. Cấm ghi vào site chính thức `sites/FRA` (`FRA - Data`) cho tới khi có quyết định mới (ADR 0020 §0); publisher từ chối đích này. Thư mục `FRA_DataIngestion - news-scape` trên OneDrive là bản cũ, không chạy mã từ đó.

```powershell
& "C:\venvs\news-scape\Scripts\Activate.ps1"      # once per terminal
# or call directly: & "C:\venvs\news-scape\Scripts\python.exe" <script_path>

cd project
python -m src.morninger            # daytime pipeline (capture + re-derive Silver + drift)
python scripts/run_once.py         # one cycle
python -m pytest tests/ -v         # tests (read docs/INDEX.md facts on pytest and the real DB first)
python -m src.monitor.health       # health check

python scripts/pipeline_radar.py status                  # touchpoints and exactly one next command
python scripts/article_run.py --where                    # paths, cwd, DB write access (0 token)
python scripts/article_run.py --wave <code> --date <day> --limit <n> --batch 100   # prepare a wave
python scripts/article_run.py --wave <code> --finish     # expand, ingest, post-check, ledger, handoff
python scripts/write_user_output.py --date today         # delivery

python scripts/ops_daemon.py status                      # autonomous operation while the machine is on (ADR-0012): level, wave, breaker
python scripts/ops_daemon.py once                        # one sensor + probe pass, opens no wave
python scripts/ops_console.py                            # text console (Ctrl+Alt+O)
python scripts/ops_daemon.py open                        # multi-agent supervision room (ADR-0014)
```

Unattended operation belongs to `ops_daemon` (Task Scheduler `news-scape-ops`); runbook `project/docs/operations/ops-daemon.md`. While the daemon runs at level L1 or higher, do not open a manual wave in parallel.

Every `scripts/...` command runs with cwd = `project/`. The operational DB is `C:\data\news-scape\monocle.db`, outside the repository. The DSH `workspace-write` sandbox cannot reach outside the repository, so `--finish` and `write_user_output.py` run with `danger-full-access`. Wave preparation and model runs do not need it.

## 5. Harness map (read only what the phase needs)

| Document | Purpose |
|---|---|
| [docs/INDEX.md](docs/INDEX.md) | Generated index of every governed knowledge document. |
| [docs/knowledge/README.md](docs/knowledge/README.md) | Knowledge contract: types, ids, frontmatter, language, lint codes. |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Vocabulary (read once). |
| [docs/HARNESS.md](docs/HARNESS.md) | Collaboration model, change loop, definition of done. |
| [docs/FEATURE_INTAKE.md](docs/FEATURE_INTAKE.md) | Risk classification to lane (before any change). |
| [docs/CONTEXT_RULES.md](docs/CONTEXT_RULES.md) | Bounded context and token budgets (phase x lane). |
| [docs/TRACE_SPEC.md](docs/TRACE_SPEC.md) | Three-tier trace schema and scoring. |
| [docs/HARNESS_COMPONENTS.md](docs/HARNESS_COMPONENTS.md) | Eleven runtime responsibilities. |
| [docs/HARNESS_MATURITY.md](docs/HARNESS_MATURITY.md) | H0-H5 maturity ladder. |
| [docs/TOOL_REGISTRY.md](docs/TOOL_REGISTRY.md) | Tool manifest and degrade ladder. |
| [docs/HARNESS_AUDIT.md](docs/HARNESS_AUDIT.md) | Entropy scoring and drift checks, including codebase hygiene. |
| [docs/IMPROVEMENT_PROTOCOL.md](docs/IMPROVEMENT_PROTOCOL.md) | Closed-loop proposals and outcome measurement. |
| [docs/TEST_MATRIX.md](docs/TEST_MATRIX.md) | Proof vocabulary and live proof table query. |
| [docs/SESSION-LATEST.md](docs/SESSION-LATEST.md) | Where am I, what next: read at start, overwrite at end. |
| [docs/OPEN-ITEMS.md](docs/OPEN-ITEMS.md) | Open items on the delivery path: blockers, rollout steps, pending decisions. |

## 6. Harness CLI (durable layer H2-H5)

```powershell
python scripts/harness_cli.py query contract        # harness capabilities and schema state
python scripts/harness_cli.py query matrix          # live story proof matrix
python scripts/harness_cli.py audit                 # entropy, drift and knowledge-contract audit
python scripts/harness_cli.py audit --codebase      # plus git hygiene, AST, conflicts
python scripts/harness_cli.py propose               # self-improvement proposals
python scripts/harness_cli.py doc new --type adr --title "..."   # allocate id, scaffold from template
python scripts/harness_cli.py doc lint              # validate governed documents (ADR-0021)
python scripts/harness_cli.py doc index             # regenerate docs/INDEX.md
python scripts/harness_cli.py doc sync              # derive story/decision rows in harness.db from files
```

## 7. Architecture boundaries and invariants

- The Article Lane is the only processing path (ADR-0010). The two-tier L1/Gold lane (`l1_route` to `agent_l1` to `agent_export` to `agent_gold`) is retired: not in presets, scheduler, radar or pipeline. Never call `l1_route.py`, `l1_ingest.py --code-first`, `agent_export.py` or `requeue.py`.
- Capture everything, process later (ADR-0013, rule 10). Every article a source has is fetched. The crawl layer filters nothing by similarity, section or relevance and never stops hard at page 1. Every discovered URL leaves a trace in the discovery ledger. Dedup, cleaning and prioritization happen after Bronze and never delete articles. Duplicates keep every source and timestamp because coverage frequency is a signal.

### 7.1 Split of work: deterministic scripts (0 token) versus agents

1. Deterministic scripts (0 token):
   - Bronze: crawl and store immutable originals (`raw_html` + `.meta.json`) for audit and SHA256 reconciliation.
   - Silver: normalize the DOM, SimHash, split content into paragraphs (`<p>`).
   - Wave packing (`article_run.py` to `article_pack.py`): select articles not yet analysed by a model, rank priority tiers, write packets to `data/agent_tasks/article/`, generate `wave_<code>.conductor.ts`.
   - Wave finish (`article_run.py --finish`): expand compact records into both schemas, ingest through the DoD gate (`l1_ingest.py`, `agent_ingest.py`, only this wave's files), post-check coverage, write the token ledger, produce the handoff.
   - Delivery: route by watchlist, export `users/output/<user>/<date>.xlsx`.
2. Agent `article-processor` (on any interchangeable LLM runtime: DSH `agent_article`, `agy`, `opencode`, `openrouter`, Claude or Codex, see FACT-llm-runtimes-are-interchangeable; no tools, exactly one step per batch) processes one whole article per pass, covering both business layers:
   - Entity recognition from title and body: tickers, companies, exchanges, sectors, indices, macro, output `l1-entity-output-v1`.
   - Content analysis: summary, arguments, market implication, `sentiment`, `time_sensitivity`, citations by paragraph index, output `agent-output-v2-lean`.
   - Clean output: no `materiality`, `event_type` or `impact_area`; these fields are retired at every layer.

### 7.2 Article Lane invariants

- One wave is one `run_code` call. The conductor session runs the whole `wave_<code>.conductor.ts` in one step: read all packets, warm the cache, run all batches in parallel, write outputs to disk, return only numbers.
- `--batch` is the only way to split batches. No token or context ceiling splits batches. A batch that returns missing articles is re-packed with `--repair` for exactly the missing part.
- Tokens are recorded, never gated. No token limit or warning threshold exists per article, batch or wave. The ledger (`token_ledger`, worker sessions only) records tokens and USD for the operator's own judgement. Never stop a wave, reduce article count or shrink batches because of tokens.
- Read full content. Packets carry every paragraph verbatim (the distillation ceiling is off). Keep only title and paragraphs; drop links, images, menus. No line exceeds the reader tool's line cap.
- Citations by paragraph index. The model returns indices; the script rebuilds verbatim paragraphs, so citations are verbatim by construction.
- Every article is fully processed. Watchlist tiers (tracked tickers, related sectors, urgent macro) decide order, not depth. Subscriber gating is gone. One exception (ADR-0016): `copy` articles (exact duplicate, or containment of at least 0.95 with the same figures and tickers) skip the packet and inherit results from the original with `l1_source = 'inherited'`. Rewrites and same-event articles are still fully analysed.
- Deterministic matching checks, it never replaces. The catalog matcher (with `Capitalized Suffix Guard` and `Prefix Guard`) cross-checks model output. Code-first output never counts as analysed (`l1_source = 'code_first'` is excluded from every count and from the selector).
- The real gate of a wave is technical: DB writable (checked before spending tokens), ingest without errors, wave coverage at least 90% in both layers. Only then does `--finish` exit 0 and print the wave-complete line.
- Bronze originals are preserved: `raw_html` and `meta.json` stay untouched for audit.

### 7.3 No script emulation of agent intelligence

- Never write a script that replaces the agent. No regex or heuristic produces recognition or analysis results.
- Semantics, entity extraction, summaries, implications and citations belong to `article-processor`, called through `tools.agent_article` in the conductor program. Every provider and model passes one output contract and one validator (ADR-0017, rule 11). A new provider must pass the golden set; agy is the benchmark; `claude` is not yet in the lane. ADR-0009 D6 (every model is `deepseek-flash`) no longer holds.
- Zero-hallucination user manifest: delivery reports reference only users enabled in `project/config/entities/manifest.yaml`. Look them up with `pipeline_radar.py users`; never copy the list into documents.

## 8. Code quality and docstrings

Detail: `.agents/rules/06-code-and-docstring-standards.md`.

- Google style: line 1 is an imperative sentence ending with a period; `Args:`, `Returns:`, `Raises:` with types and short descriptions. Module docstring is exactly one declarative sentence.
- No filler, no first person, no rhetorical questions, no emoji, no temporary tags (`[LEGACY]`, temporary TODO).
- Docstrings and comments state inputs, behaviour, outputs and non-obvious logic only. No debugging diary or history in source.
- Every code change passes `ast.parse` and the unit tests (`pytest tests/`).

## 9. Zero-probe context and continuous learning

Detail: `.agents/rules/08-context-and-zero-probe-guardrails.md`.

- Radar first, never probe. Ad-hoc Python one-liners (`-c "import sqlite3..."`) or file sweeps just to gain context are forbidden. Every operating session starts with:
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/pipeline_radar.py status
  ```
  Radar reports pipeline state and exactly one next command for the Article Lane wave lifecycle. Path, cwd and DB write questions go to `project/scripts/article_run.py --where`. A question neither command answers is reported as a missing command, not answered by digging through source.
- Conductor and auditor roles are separate. Zero-probe binds the conductor session. A post-wave audit session may read code and run read-only queries, but every finding ends in a command or a script patch.
- Progressive bounded context: never load huge dictionaries (`entities.json`, 1.5 MB) or raw folder dumps. Start from at most three files: `AGENTS.md`, `docs/SESSION-LATEST.md`, the relevant skill. Use `docs/INDEX.md` to find the rest.
- Continuous policy distillation: every friction found (permission timeout, better flag, new entity) becomes a `FACT-*` document, a rule or a skill update before the session closes, so later agents inherit it.

## 10. Infrastructure gate before operating on DSH (applies whenever DSH is the chosen runtime)

Detail: `.agents/rules/09-dsh-preflight-gate.md`.

- No wave command before the gate. Every DSH session passes 14 preflight items in one `run_code` call (0 token) and answers "is the infrastructure ready for a wave command?" with measurements.
- Trust runtime, not YAML. Presets load at mount time. Compare the `StartTime` of the port-3080 process with the `LastWriteTime` of `agent.cordis.yml`: a newer file means the edit is not active yet, and the only symptom is a wrong bill.
- Mount-time files (`agent.cordis.yml`, `preset.yml`, `~/.dsh/settings.yaml`) need a host restart; live files (`skills/**/SKILL.md`, `.agents/rules/*.md`, runbooks, Python scripts) do not. Check the table in the rule before concluding.
- No grey items. Each item is RED or GREEN; "probably fine" is RED, and RED blocks the wave.
- Restarting the host and opening a new session are different. Restart means stopping and starting `dsh web` (the conductor cannot do it from inside). A new session is an operator action in the UI, with the preset chosen before the first message.

## 11. Capture everything, miss nothing (every crawl-layer change)

Detail: `.agents/rules/10-thu-thap-tron-ven.md`; decision ADR-0013.

- Fetch everything the source has. No filtering at the crawl layer except technical copies with the same normalized URL (still recorded as aliases).
- No "dropped" state. Every discovered URL enters the discovery ledger before any filter. Final states are only `captured`, `alias`, `gone` or `dead_letter` with a reason.
- Paginate by watermark, backfill after the machine was off, reconcile with sitemaps daily. A daily shortfall above 2% against the reconciliation channel is RED.
- Duplicates are data. They may skip the LLM but are always kept and counted in frequency and coverage-breadth metrics.

## 12. Session closure and mechanical git governance

- No dangling dirty tree. Every session that changes code or documents runs `& "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py git status`. If `clean_for_closure` is false, the session is not complete.
- Commits follow Conventional Commits (at most 72 characters, carrying `(US-NNN)`), generated with `harness_cli.py git template`, and are pushed (`git push origin <branch>`) before `docs/SESSION-LATEST.md` is handed off.
