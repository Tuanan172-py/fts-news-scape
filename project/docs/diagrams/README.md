# news-scape operations diagrams

The complete operating workflow of the project, readable on a local machine with no network (ADR-0026, US-048). The logic comes from [`../design/00-end-to-end-architecture.md`](../design/00-end-to-end-architecture.md); when the two disagree, that document prevails.

## How to view

Open `index.html` in a browser. It is one self-contained file written as a working paper: an abstract, an interactive six-layer map (Figure 1), six tables (system facts, layers, data stores, invariants, decisions, open items) and 16 detail diagrams (Figures 2 to 17). It needs no network, and a copy of the file alone is enough to share it. Print with Ctrl+P on A4 landscape, or use the "Print or save as PDF" button.

The `.mmd` files are the sources of the "Detail diagrams" section. There is no need to open them separately.

## Contents

| File | Content |
|------|---------|
| `00-context.mmd` | C4 level 1: people, news sources, LLM runners, SharePoint |
| `01-containers.mmd` | C4 level 2: the six layers and the data stores |
| `10` to `15` | One diagram per layer: L0 control, L1 capture, L2 Silver, L3 Article Lane, L4 Lakehouse, L5 Harness |
| `20-flow-main.mmd` | Main data flow from source to analyst |
| `21-flow-wave.mmd` | Life of a wave opened by the daemon |
| `22-flow-capture.mmd` | Complete capture and reconciliation |
| `23-flow-publish.mmd` | Publishing: `publish.py` calls `publish_day()` |
| `24-flow-delivery.mmd` | Excel delivery, user manifest and the `users/output` tree |
| `25-flow-session-close.mmd` | Closing a harness session: record, do not block |
| `30-state-levels.mmd` | Autonomy levels L0 and L1 |
| `31-runner-order.mmd` | Runner order: agy, `opencode run`, OpenRouter |

## Conventions

- The presentation standard comes from the `report_writing_skills` collection (academic HTML reports and enterprise writing style), selected for an operations document: one light, monochrome theme (black, grey, white), serif text, sans-serif tables and captions, booktabs tables, and continuously numbered figures and tables with the caption below a figure and above a table.
- The text is English: complete sentences, no hype phrases, no emoji or decorative symbols, no pill labels or rounded KPI cards, and no fragments chained with middle dots or arrows. `tests/test_diagrams.py` checks these rules in `map.template.html` and in every `.mmd` file.
- Meaning is carried by shape and line style, not by colour. In the map, a solid line is data flow, a dashed line is control, a dotted line is a read, and a dash-dot line is governance. In the Mermaid diagrams, a dashed border is a gate, a thick border is a passing result, a dotted border is a failure or a forbidden action, and a grey fill is a data store or an external system.
- `map.template.html` holds the map, the tables and the prose; edit it there. The `*.mmd` files are the detail diagrams; the first lines `%% title:` and `%% desc:` supply the figure title and its note.
- After an edit, run `python scripts/docs/build_diagrams.py` from `project/` to rebuild `index.html`. `--check` only reports whether the file is stale.
- Quote Mermaid labels that contain special characters. Use `flowchart`, not `graph`. Draw a gate as a rectangle with `class gate`, not as a diamond, so that diagrams stay compact.
- File names in the `files:[...]` blocks of the map and in `.mmd` labels must exist in the repository; `tests/test_diagrams.py` checks this.
- Do not use Georgia for Vietnamese text. This document is English, so the standard serif stack applies. No font is loaded from the network.
- `vendor/mermaid.min.js` is version-pinned (see `vendor/VERSION.txt`) and inlined into `index.html`. Do not switch to a CDN.
