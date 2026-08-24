# AGENTS.md — Entrypoint & authority gate (news-scape)

> Read this FIRST every session. It is a small, stable shim. Detail lives in `docs/`.
> **App is what users touch. The harness is what agents touch.**

## 0. Rule number one — classify the request BEFORE any operation

```
Incoming request
  └─ Only needs: answer / explain / review / diagnose / plan / status ?
       ├─ YES → READ-ONLY. Read only the files needed → answer → STOP.
       │        Do NOT create/edit files, DB, config, stories, or traces.
       └─ NO  → CHANGE (build / fix / "apply the fix for me").
                Run the change loop in docs/HARNESS.md (intake first).
```

Boundary example: "Why is this scraper failing?" = read-only even if you spot a config bug — diagnosing ≠ fixing. "Fix that scraper" = change → intake first.

## 1. WIP = 1

At most **one** story `in_progress` at a time. If an urgent request interrupts, park the current story (`blocked` or `deferred`, with reason) BEFORE starting the new one. Never two `in_progress`.

## 2. OKF — where to get product context (priority order)

Read these before inventing context; do NOT create a new knowledge folder:
1. `project/docs/skills/*` — per-domain scraper knowledge (cafef, fireant, rss-sources, tnck).
2. `project/docs/{design,dev,domains,operations}/` — architecture, how-tos, source taxonomy, ops.
3. `project/docs/charter.md` + `project/docs/ARCHITECTURE.md` — goals, phases, TDRs.
4. repo `okf/` — cross-cutting operational knowledge.

## 3. Project build / run (the product lives in `project/`)

```powershell
cd project
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
python -m src.morninger            # daytime pipeline (capture + re-derive Silver + drift)
python scripts/run_once.py         # one cycle
python -m pytest tests/ -v         # tests
python -m src.monitor.health       # health check
```

## 4. Harness map (read as the phase needs — bounded context)

| Doc | Purpose |
|-----|---------|
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Vocabulary (read once). |
| [docs/HARNESS.md](docs/HARNESS.md) | The collaboration model + change loop + Done definition. |
| [docs/FEATURE_INTAKE.md](docs/FEATURE_INTAKE.md) | Risk classification → lane (do this before any change). |
| [docs/CONTEXT_RULES.md](docs/CONTEXT_RULES.md) | Bounded context & token budgets (Phase × Lane). |
| [docs/TRACE_SPEC.md](docs/TRACE_SPEC.md) | 3-tier trace schema & scoring specification. |
| [docs/HARNESS_COMPONENTS.md](docs/HARNESS_COMPONENTS.md) | 11 runtime responsibilities. |
| [docs/HARNESS_MATURITY.md](docs/HARNESS_MATURITY.md) | H0–H5 maturity ladder & criteria. |
| [docs/TOOL_REGISTRY.md](docs/TOOL_REGISTRY.md) | Tool manifest & degrade ladder. |
| [docs/HARNESS_AUDIT.md](docs/HARNESS_AUDIT.md) | Entropy scoring & 6 drift checks. |
| [docs/IMPROVEMENT_PROTOCOL.md](docs/IMPROVEMENT_PROTOCOL.md) | Closed-loop propose & outcome measurement. |
| [docs/TEST_MATRIX.md](docs/TEST_MATRIX.md) | Proof vocabulary & live proof table query. |
| [docs/SESSION-LATEST.md](docs/SESSION-LATEST.md) | "Where am I, what next" — read at start, overwrite at end. |

## 5. Harness CLI (Durable Layer H2-H5)

```powershell
python scripts/harness_cli.py query contract   # Check harness capabilities & schema state
python scripts/harness_cli.py query matrix     # Query live story proof matrix
python scripts/harness_cli.py audit            # Run entropy & drift audit
python scripts/harness_cli.py propose          # Generate self-improvement proposals
```

Maturity: this harness is at **H2-H5 (Durable SQLite + Active Observability + Auto-Verification + Self-Improvement Protocol)**.

