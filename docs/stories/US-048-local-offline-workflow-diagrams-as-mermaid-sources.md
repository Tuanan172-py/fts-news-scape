---
id: US-048
type: story
title: Local offline workflow diagrams as Mermaid sources
status: implemented
lane: normal
created: 2026-10-21
updated: 2026-10-21
lang: en
authors: [claude]
adr: [ADR-0026]
plan: []
evidence:
  - path:project/docs/diagrams/README.md
  - path:project/scripts/docs/build_diagrams.py
  - test:project/tests/repo/test_diagrams.py
verify: "cd project && python -m pytest tests/repo/test_diagrams.py -q"
summary: The whole operating workflow opens offline as one self-contained HTML page with an interactive six-layer map and per-flow diagrams, replacing the Claude-only artifact.
---

# US-048 — Local offline workflow diagrams as Mermaid sources

## Contract

The whole operating workflow of the project MUST be readable in one place on the operating machine with no network and no Claude session. One self-contained HTML file carries the interactive layer map, the reference tables and the per-flow diagrams, so a reader never has to open separate diagram files. The page is a circulation document laid out as a working paper (monochrome, serif text, booktabs tables, numbered figures); it prints to A4 landscape. The logic is the one already approved in the architecture map; only the form and the place change.

## Acceptance Criteria

- [x] `project/docs/diagrams/index.html` is one file generated from `map.template.html`, the `*.mmd` sources and a pinned Mermaid; it has no external URL and no external font.
- [x] The interactive map (six layers, five flow modes, detail drawer) and six numbered tables reflect ADR-0026. Tables cover the system, layers, stores, invariants, ADR ledger and open items. ADR-0026 means L0/L1 only, one publish path, runner order, one manifest and `users/output`.
- [x] Presentation follows the operator's report standards (`report_writing_skills`: STANDARD S2, S3, S4, S7 and the banned-phrase lists): monochrome palette, no emoji or decorative symbols, no hype phrases, no pill labels; `test_map_text_follows_report_standards` enforces it.
- [x] 16 detail diagrams render in Edge headless with no syntax error; the page shows one at a time.
- [x] `tests/repo/test_diagrams.py` checks diagram kind, file names in labels and in map nodes, and that `index.html` is current.
- [x] design 00, `project/docs/README.md`, `AGENTS.md` and OPEN-ITEMS point to the diagrams.
- [x] Operator reviewed the working-paper version and confirmed the layout (2026-10-22).

## Design Notes

- Selective adoption of the external research: Diagram-as-Code, Mermaid and the C4 layering only. D2, PlantUML, Kroki, Excalidraw, BPMN, LangGraph Studio and Langfuse were rejected because they need extra binaries or duplicate the existing `ops_spans` and DBOS tracing.
- The map keeps its own tables; design 00 stays the text source of truth and wins on conflict.
- Mermaid 11.4.1 is vendored (2.5 MB, MIT) and inlined, so a single copied file works anywhere. Its colours come from the page palette through CSS (ink, grey, white); status is shown by line style, not colour.
- Serif stack skips Georgia because it lacks stacked Vietnamese diacritics (observed in Edge); Cambria and Times New Roman are used instead.
- The first version used colour-coded layers and pill buttons; the operator judged it still looked machine-made, so it was rebuilt on the working-paper standard.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest tests/repo/test_diagrams.py` | 36 passed |
| Platform | Edge headless `--dump-dom` and screenshots | 16 Mermaid svg, 0 errors; map, drawer and all 5 flow modes work; print produces 36 A4 landscape pages (layout not inspected visually) |

## Evidence

