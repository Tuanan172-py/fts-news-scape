# OKF Deep Integration — Web Monocle (news-scape)

**Ngày:** 2026-08-17 | **Trạng thái:** Planned | **Owner:** knowledge-manager role
**Nguyên tắc:** LOCAL-FIRST · Python-native · Từ từ chắc chắn · YAGNI/KISS/DRY

## Overview
Biến OKF (Open Knowledge Format v0.2, markdown+frontmatter trong git) thành lớp tri thức bền vững cho Web Monocle: từ KB tĩnh (GĐ1) → tooling Python validate/codegen + agent read-only (GĐ2) → knowledge-graph truy vấn được (GĐ3). KHÔNG GCP/Dataplex/BigQuery. OKF là **track độc lập** với harness; chỉ giao tiếp ở ranh giới rõ ràng.

## 2 Quyết Định Nền Tảng

### Quyết định A — OKF vs nested git repo upstream
`okf/` hiện là clone của `GoogleCloudPlatform/knowledge-catalog` (có `.git` riêng, remote = upstream) NHƯNG repo cha cũng snapshot 296 file của nó → drift version.
**KHUYẾN NGHỊ (chọn):** *Vendor-pin + tách content khỏi tooling.*
1. Xoá `okf/.git` (kill nested repo) → hết drift 2 chiều. Ghi commit-hash upstream đã pin vào `okf/VENDOR.md`.
2. Xoá boilerplate Google không dùng: `okf/README.md`, `okf/SPEC.md`(root), `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `okf/toolbox/` (TS), `okf/samples/`.
3. Giữ vendored (reference-only, KHÔNG chạy runtime): `okf/okf/src/reference_agent/bundle/document.py` (parser), `viewer/` (viz Cytoscape), `SPEC.md` — đưa vào `okf/_vendor/` + LICENSE Apache-2.0.
4. Content Web Monocle KB dời vào `okf/catalog/` (xem Quyết định B).
*Lý do:* subtree/submodule thêm phức tạp vận hành cho 1 lần pin (YAGNI). Ta chỉ cần đọc pattern + vài file parser.

### Quyết định B — Một nhà canonical duy nhất cho KB
Xung đột: harness H1 tuyên bố `project/docs/skills/*` + design/dev/domains = "OKF"; song song KB populated thật nằm ở `okf/` root → **hai nhà "OKF"**.
**KHUYẾN NGHỊ (chọn):** *`okf/catalog/` = nhà canonical DUY NHẤT cho OKF concepts.* `project/docs/**` = **sources** (tài liệu người viết), KHÔNG phải OKF concepts.
- Dời 30 file KB `okf/{tables,pipelines,metrics,...}` → `okf/catalog/{...}` (append-only, giữ nội dung).
- Frontmatter `sources[].resource` vẫn trỏ về `project/docs/**` + `project/src/**` (provenance nguyên vẹn).
- Tôn trọng harness "no `knowledge/` folder": KHÔNG tạo `knowledge/`. `project/docs/skills/*` giữ nguyên vai trò skill-docs, được OKF **tham chiếu** (sources), không bị nhân bản. Redirect: `okf/index.md` + `okf/MAPPING.md` là điểm vào duy nhất.

## Nguyên tắc xuyên suốt (cross-cutting)

### Quy tắc DURABLE vs LIVE (giải mâu thuẫn "live-markdown = anti-pattern")
OKF chỉ chứa **tri thức bền vững**: schema, thiết kế, ngữ nghĩa domain, quyết định (ADR), pattern query. **TUYỆT ĐỐI KHÔNG** chứa trạng thái runtime (số bài/ngày, health, dedup-rate hiện thời) — cái đó ở DB/logs. Metric docs trong OKF mô tả *định nghĩa* metric, KHÔNG lưu giá trị. → giải đúng phản đối của harness H1.

### Bảng ranh giới OKF ↔ code ↔ harness ↔ agent
| Surface | Ai ĐỌC | Ai GHI | Khi nào | Qua công cụ |
|---|---|---|---|---|
| `okf/catalog/*.md` | agent, harness, human | tooling `okftools`, human knowledge-manager | trên PR/pre-commit; khi story done | Edit thủ công + `okf gen-domain` |
| domain YAML (23) | pipeline loader `config.py` | human (existing); tooling chỉ GHI domain MỚI | append-only | `okf validate-domains` / `gen-domain` |
| `store.py` _SCHEMA | pipeline | dev (KHÔNG phải OKF) | — | `okf validate` chỉ đọc & so drift |
| harness story/DoD template | human | GĐ1 chèn checklist | khi tạo template | Edit |
| agent (Claude/GPT) | OKF read-only | KHÔNG bao giờ ghi OKF | export-tasks | qua capability GĐ2 |

**Permissions:** OKF chỉ được ghi bởi (a) tooling `okftools` hoặc (b) human role knowledge-manager. Agent không mutate OKF không dấu vết (mọi thay đổi có frontmatter `generated:{by,at}` + provenance `sources:`).

### Phụ thuộc harness & degrade gracefully
- GĐ2 pre-commit + GĐ3 observability **phụ thuộc** harness leo H1→H2 (CLI/SQLite/CONTEXT_RULES/TRACE_SPEC chưa build).
- **Fallback standalone:** nếu harness kẹt ở H1 → `okftools` vẫn chạy độc lập (git mtime thay cho SQLite trace; pre-commit hook cục bộ thay cho harness gate). OKF KHÔNG phụ thuộc harness internals.

## Tiến độ thực thi
- **2026-08-18 (1):** Quyết định A + B ĐÃ THỰC THI (staged, chưa commit):
  - Xóa nested `okf/.git`; pin upstream `3fcbb9f` lưu ở `okf/_vendor/VENDOR.md`.
  - Xóa 265 file upstream Google (`okf/okf`, `toolbox`, `samples`, boilerplate).
  - `git mv` 29 KB file → `okf/catalog/` (nhà canonical duy nhất).
  - Tạo `okf/MAPPING.md`; cập nhật `okf/index.md`; giữ reference-only ở `okf/_vendor/`.
- **2026-08-18 (2):** `okf/tools/okf_check.py` (+ README) — lệnh `outdated` (git/fs-mtime, --all/--json/--no-git), exit-code gate.
  - Kết quả chạy đầu: 22 file · 8 stale (drift thật do `store.py` đổi 17/08) · 3 no-source (metrics) · 0 parse-error.
  - Vệ sinh dữ liệu: quote `resource:` 4 file `tables/*` (YAML hợp lệ).
  - CÒN LẠI GĐ1: (i) knowledge-manager review 8 stale + bump `sources_last_checked`; (ii) checklist "OKF Updates Required" vào story/DoD template.

## Bảng Phase
| Phase | Mục tiêu | Thời lượng | Status | Progress | Link |
|---|---|---|---|---|---|
| GĐ1 Static Foundation | KB tĩnh có kỷ luật, cập nhật thủ công | ~2 tuần | In progress | ~70% (A+B + `okf-check` xong; còn review-stale + checklist DoD) | [phase-01](phase-01-static-foundation.md) |
| GĐ2 Semi-Automation | code+agent tiêu thụ OKF; auto-update một phần | ~2 tháng | Planned | 0% | [phase-02](phase-02-semi-automation.md) |
| GĐ3 Living Knowledge Graph | KB truy vấn được, tự cải thiện (far-future) | 2–6 tháng | Planned | 0% | [phase-03](phase-03-living-knowledge-graph.md) |

## Top Risks
1. **Xoá nested `.git` mất lịch sử upstream** → ghi commit-hash vào `okf/_vendor/VENDOR.md` trước khi xoá; backup ngoài repo.
2. **Drift OKF↔store.py↔YAML** khi code đổi mà KB không đổi → `okf-check outdated` (GĐ1) + `okf validate` pre-commit (GĐ2).
3. **Hai nhà OKF gây nhầm** → Quyết định B fix; `okf/MAPPING.md` là nguồn duy nhất về vị trí.
4. **Harness chưa lên H2** chặn GĐ2/3 → fallback standalone git-mtime.
5. **OneDrive path có space + `.git` nested** → luôn quote path; test `okftools` trên path có khoảng trắng.

## Open Questions
1. Entity model: dùng type OKF chung (SQLite Table, Pipeline) hay thêm domain-specific (NewsSource)? → đề xuất giữ chung, chốt GĐ2.
2. `okf/_vendor/` có commit vào git cha hay gitignore + tải lại khi cần? (ưu: commit để reproducible; nhược: +296 file).
3. Charter OKF (harness dùng `plans/.../charter.md`) có gộp vào `okf/catalog/` không, hay giữ ở plans? → GĐ2 quyết.
4. Ngưỡng "stale" trong `okf-check outdated`: git mtime vs `sources_last_checked` frontmatter — chọn cái nào làm chuẩn khi lệch?
5. GĐ3 JSON-LD context/ontology: tự định nghĩa hay mượn schema.org/DCAT? (chưa cần build).
