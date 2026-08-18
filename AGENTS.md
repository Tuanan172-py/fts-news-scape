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
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Harness↔product boundary (pointer to product docs). |
| [docs/TEST_MATRIX.md](docs/TEST_MATRIX.md) | Proof vocabulary + live proof table. |
| [docs/SESSION-LATEST.md](docs/SESSION-LATEST.md) | "Where am I, what next" — read at start, overwrite at end. |
| [docs/HARNESS_BACKLOG.md](docs/HARNESS_BACKLOG.md) | Friction reservoir — file pain here. |
| `harness/HARNESS_RUNBOOK.md`, `harness/HARNESS_BUILD_FROM_SCRATCH.md` | Reference (full/mature harness). |

Maturity: this harness is at **H1 (pure markdown, no database)**. Climb to H2 only when markdown hurts (see docs/HARNESS.md).
