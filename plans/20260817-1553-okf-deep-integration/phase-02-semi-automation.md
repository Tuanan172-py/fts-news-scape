# GĐ2 — Semi-Automation (~2 tháng)

## Context links
- [plan.md](plan.md) · [phase-01](phase-01-static-foundation.md) · [researcher-01](research/researcher-01-okf-format-tooling.md) · [researcher-02](research/researcher-02-newsscape-surfaces.md)
- Phụ thuộc: harness H2 (CLI/SQLite/CONTEXT_RULES/TRACE_SPEC) — có fallback standalone.

## Overview
- **Ngày:** 2026-08-17 | **Priority:** P1 (bắt đầu chỉ khi GĐ1 stable)
- **Mô tả:** OKF được code + agent tiêu thụ; auto-update một phần. Dựng package `okftools/`, drift-validate, gen-domain, agent read-only capability.
- **Impl-status:** Not started | **Review-status:** Pending

## Key Insights
- `store.py` _SCHEMA = source of truth DDL (articles + 7 bảng phụ). OKF `catalog/tables/*.md` có bảng Schema markdown → so được cột/type.
- `config.py` chỉ hard-enforce `{name, method}`, còn lại default → validate dễ, generate an toàn (append-only).
- Project đã có văn hoá schema-validation (JSON-schema + dod.py 5-predicate) → wire pre-commit khớp văn hoá.
- Agent framework (`AgentRunner`) đã có ranh giới đọc/ghi rõ (work-package-v1 in, agent-output-v1 out) → capability OKF chỉ thêm nguồn đọc read-only.

## Requirements
- R1: Package `okftools/` (parser, model, graph, cli).
- R2: `okf validate` — drift OKF tables ↔ store.py DDL + OKF configurations ↔ domain YAML.
- R3: Pre-commit hook chạy `okf validate` (fallback: git hook cục bộ nếu harness chưa có gate).
- R4: `okf validate-domains` (23, VALIDATE) + `okf gen-domain <name>` (NEW only, GENERATE).
- R5: Agent read-only capability trả lời architecture/data-flow/domain từ OKF (KHÔNG ghi).
- R6: Backward-compatible tuyệt đối (VALIDATE-over-GENERATE cho config cũ).

## Architecture
```
okftools/                      # NEW python package (thay scripts/okf_check.py GĐ1)
  __init__.py
  parser.py     # python-frontmatter: đọc/ghi concept .md
  model.py      # pydantic v2: OKFConcept, Source, Generated, TableSchema, DomainConfig
  graph.py      # networkx: nodes=concept, edges=links + sources
  drift.py      # so store.py _SCHEMA ↔ tables/*.md ; YAML ↔ configurations/*
  domains.py    # validate 23 + gen-domain (frontmatter→YAML, append-only)
  cli.py        # click/typer: okf check|sync|graph|validate|validate-domains|gen-domain
  agent_view.py # read-only API: query(concept|dataflow|domain) → text
pyproject.toml  # deps: python-frontmatter, pydantic>=2, networkx, click; NO node
.pre-commit-config.yaml  # hook: okf validate
```
- **Drift `store.py`:** parse `_SCHEMA` DDL bằng regex/`sqlparse` (nhẹ) → set(cột,type,constraint) so với bảng markdown trong `articles.md`. Rule: cột bị XOÁ/RENAME → FAIL; cột thêm cuối / reorder → WARN (backward-compat).
- **gen-domain:** đọc concept `configurations/*.md` frontmatter cho domain MỚI → render `config/domains/<name>.yaml`. TỪ CHỐI ghi đè nếu file tồn tại (append-only, YAGNI).
- **Agent capability (R5):** hàm thuần đọc `catalog/`, trả prose + link. Ranh giới: agent gọi `okf_view.query(...)`, KHÔNG có code path ghi. Khớp bảng ranh giới plan.md.

## Related code files (real paths)
- `project/src/db/store.py` (_SCHEMA, chỉ đọc — mục tiêu drift)
- `project/src/core/config.py` (`load_domain_config`, `list_domains` — tham chiếu schema)
- `project/config/domains/*.yaml` (23, VALIDATE) · `project/config/domains.yaml` (registry)
- `okf/catalog/tables/*.md` · `okf/catalog/configurations/*.md`
- `project/schemas/*.schema.json` (giữ nguyên; đảm bảo tương thích)
- `okf/_vendor/document.py` (tham chiếu parser pattern — KHÔNG import runtime)
- `okftools/**` (NEW) · `.pre-commit-config.yaml` (NEW)
- `project/src/agent/runner.py` (điểm nối agent capability read-only)

## Implementation Steps
1. **Scaffold `okftools/`** + pyproject (pin deps, KHÔNG node). Port `okf_check.py` GĐ1 vào `cli.py check`.
2. **`model.py`:** pydantic v2 cho frontmatter (Source/Generated/status/tags) + `TableSchema`(cột) + `DomainConfig`(name,method,rate_limit,timeout,...). Discriminated union theo `type`.
3. **`parser.py`:** wrap python-frontmatter, round-trip an toàn (giữ body, footnotes).
4. **`drift.py` + `okf validate`:** parse store.py `_SCHEMA` → so `articles.md`; parse YAML → so `configurations/domain_sources.md`. Exit code ≠0 khi drift cứng.
5. **`domains.py`:** `validate-domains` (23, load qua logic giống config.py, so frontmatter) + `gen-domain` (render YAML mới, refuse-overwrite).
6. **Pre-commit (R3):** `.pre-commit-config.yaml` chạy `okf validate`. Fallback: `.git/hooks/pre-commit` script gọi `python -m okftools.cli validate` nếu harness chưa cung cấp gate.
7. **`graph.py`:** build networkx từ links + sources; `okf graph` export dict/JSON (chuẩn bị GĐ3).
8. **`agent_view.py` (R5):** API `query()` read-only; document ranh giới trong `okf/MAPPING.md`. Nối tuỳ chọn vào `runner.py` (chỉ đọc).
9. **Tests pytest:** drift positive/negative, gen-domain round-trip, validate 23 domain pass.
10. **CONTEXT_RULES nối harness (nếu H2 sẵn):** agent đọc OKF read-only theo work_package-v1; nếu H1 → capability chạy standalone.

## Todo list
- [ ] Scaffold okftools + pyproject
- [ ] pydantic model frontmatter+schema+domain
- [ ] parser round-trip
- [ ] drift.py + `okf validate` (tables↔DDL, config↔YAML)
- [ ] validate-domains (23) pass
- [ ] gen-domain (NEW only, refuse-overwrite)
- [ ] pre-commit hook + fallback git hook
- [ ] graph.py export
- [ ] agent_view read-only + ranh giới doc
- [ ] pytest suite

## Success Criteria (KPI/DoD)
- **KPI:** 80% domain config MỚI được generate từ OKF; **0 drift** trên `okf validate`.
- **DoD:** (a) `okf validate` xanh, chặn commit khi drift cứng; (b) 23 YAML pass validate KHÔNG bị sửa; (c) `gen-domain` tạo YAML hợp lệ, từ chối ghi đè; (d) agent capability chỉ-đọc, không path ghi OKF; (e) tests pass.

## Risk Assessment
- Parse DDL từ store.py giòn (regex) → mitigate: `sqlparse` + test cố định trên _SCHEMA hiện tại.
- Harness chưa H2 → pre-commit/agent chạy standalone (fallback đã thiết kế).
- gen-domain sinh YAML thiếu key `method` → validate chặn trước commit.
- pydantic v2 breaking vs v1 nếu repo pin v1 → kiểm `project` deps trước.

## Security Considerations
- `okf validate` KHÔNG thực thi code từ concept (chỉ parse text) → tránh injection.
- gen-domain không ghi secret; headers/proxy nhạy cảm để trống, human điền.
- Agent capability read-only: đảm bảo không có filesystem-write trong `agent_view.py`.

## Next steps
→ GĐ3: chuẩn hoá frontmatter → JSON-LD export; observability log OKF read/update per agent trace (harness H2 TRACE_SPEC); suggestion engine từ friction backlog; mở rộng codegen (migration/API/test fixtures).
