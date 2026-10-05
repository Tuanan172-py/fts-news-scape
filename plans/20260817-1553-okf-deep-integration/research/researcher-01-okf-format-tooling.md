# OKF Format & Tooling Research
**Date**: 2026-08-17 | **Scope**: Local-first Python integration (NO GCP/Dataplex)

---

## OKF v0.2 Frontmatter Schema

### Required
- `type` (string): Concept classification (e.g., "BigQuery Table", "API Endpoint", "Metric"). No central registry; consumers tolerate unknown types.

### Recommended
- `title`, `description`, `resource` (URI for physical asset), `tags` (YAML list)

### Trust/Provenance (§5 SPEC)
- `sources[]`: Array with `{id, resource, title, author}` + credibility signals (usage_count, last_modified)
- `verified`: Tier ("unverified" | "machine-confirmed" | "human-reviewed")
- `generated`: `{by: "<producer>/<version>"|"human:<id>"|"process:<id>", at: ISO8601}`
- `status`, `stale_after`: Lifecycle signals

### Computation (§10 SPEC)
- `type: Attested Computation` with `executor`, `receipt` shape (runtime artifact, not stored)

**Key**: Frontmatter is minimal; body = prose, schemas, example queries. No central schema registry.

---

## Linking & Graph Model

**Intra-bundle links** via standard markdown `[text](/path/to/concept.md)`.
**Cross-references**: `sources[].resource` (URIs), `links` field (entrylinks).
**Graph structure**: Concepts (nodes) = files; edges = markdown links + sources array.
**Index/progressive disclosure**: `index.md` per directory (optional, lists children).

**Backlinks**: Consumers compute reverse edges at read time (no stored backlinks).

---

## Existing OKF Python Lib Reusability

### What's in `okf/okf/src`
1. **Reference agent** (`reference_agent`): Produces OKF from BigQuery metadata + web crawl.
   - Two-pass: BQ → base docs, then LLM crawls URLs to enrich.
   - Uses Google ADK, google-cloud-bigquery, Gemini API.
   - **NOT usable** for local-only; hardcoded GCP/Gemini (see `pyproject.toml`).

2. **Visualizer** (`reference_agent.visualize`): Renders bundle → self-contained HTML.
   - Force-directed graph (Cytoscape.js), search, type filter, backlinks.
   - **Reusable**: Graph-generation logic can export to JSON for non-Cytoscape consumers.

3. **CLI entry point** (`reference_agent.cli:main`): `enrich` + `visualize` subcommands.

### What to Build (NOT in lib)
1. **Frontmatter parser**: OKF lib uses `yaml.safe_load()` (see `enrichment/util/markdown.py` — custom 150-line parser).
   - Use `python-frontmatter` lib (handles ---/--- splitting, YAML parse, body extraction).
2. **Local snapshot management**: Read/write/list concepts from disk (mimic `mdcode`'s `CatalogLayout`).
3. **Graph builder**: Traverse directory, parse links, build networkx or dict-based DAG.
4. **Manifest validation**: Pydantic v2 model for local `manifest.yaml` (mimic `catalog.yaml` from mdcode).
5. **Drift detection, indexing**: NOT in OKF lib.

---

## mdcode Reusable Concepts (Local-Only Equivalent)

**mdcode = GCP Knowledge Catalog metadata-as-code tooling; we extract pattern, no cloud API**.

| Concept | mdcode (GCP) | Local Python Equiv |
|---------|-------------|-------------------|
| **Manifest** | `catalog.yaml` scope (bq-dataset, entryGroup, kb) → drives layout strategy | `manifest.yaml`: minimal YAML listing entry patterns, root dir structure |
| **Snapshot** | Local copy of remote metadata | Directory tree of `.md` files (OKF bundle root) |
| **Layout** | Abstract; StandardLayout (YAML + .overview.md sidecars) vs WikiLayout (markdown frontmatter) | OKF uses WikiLayout only (markdown frontmatter) |
| **Pull** | Fetch from Dataplex API → write local | Discover from local source tree (git, YAML DDL, code) → infer metadata |
| **Push** | Write local changes → Dataplex API | (Optional) export to JSON-LD, markdown, or SQLite catalog |
| **Drift check** | Compare saved checksum state vs remote | Compare file mtimes vs manifest generation.at |

---

## Recommended Python Libraries

| Task | Library | Rationale |
|------|---------|-----------|
| Frontmatter parse | `python-frontmatter` (PyPI) | Standard, battle-tested, < 50 lines used |
| YAML (already shown) | `PyYAML` | OKF uses it; Pydantic can delegate parsing |
| Schema validation | `pydantic>=2.0` | Type-safe, Field validators, discriminated unions for entity types |
| Graph (DAG/links) | `networkx` or plain dict | networkx for rich graph algorithms; dict if only need traversal |
| JSON-LD export | `pyld` (Python JSON-LD lib) | For Linked Data; optional (GĐ3 compliance) |
| Tests | `pytest` | Already in OKF repo convention |

---

## Licensing & Vendoring

- **OKF repo**: Apache-2.0 (see `okf/okf/` header).
- **Nested git**: `okf/` is git submodule or separate checkout; safe to vendor samples code.
- **No IP conflict**: OKF is open; our local reimplementation OK under Apache-2.0 + project license.

---

## Unresolved Questions

1. **Entry entity model**: Do we standardize on OKF concept types (BigQuery Table, API Endpoint, Metric) or invent domain-specific ones for news-scape (NewsSource, Article, Entity)?
2. **Manifest scope**: Minimal (just root dir) or mirror mdcode's "scope" (bq-dataset/entryGroup/kb flavors)?
3. **Graph export target**: Cytoscape JSON (for viz), JSON-LD (RDF), or SQLite (search/query)?
4. **Discovery sources**: File-based (YAML config DDL, git), code-based (Python AST introspection), or static manifest only?
5. **Drift baseline**: Trust file mtimes, git commit dates, or external state file (.okf.state)?
