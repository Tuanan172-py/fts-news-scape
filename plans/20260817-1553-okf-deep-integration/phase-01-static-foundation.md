# GĐ1 — Static Foundation (~2 tuần)

## Context links
- [plan.md](plan.md) · [researcher-01](research/researcher-01-okf-format-tooling.md) · [researcher-02](research/researcher-02-newsscape-surfaces.md) · [scout-01](scout/scout-01-filemap.md)
- Harness verdict: [harness plan.md](../20260817-1536-harness-h1-newsscape/plan.md) (row 4,5: no `knowledge/`, declare-don't-fork, no live-state-md)

## Overview
- **Ngày:** 2026-08-17 | **Priority:** P0 (nền cho GĐ2/3)
- **Mô tả:** OKF = KB tĩnh có cấu trúc, cập nhật thủ công nhưng kỷ luật. Chốt Quyết định A+B, dựng mapping, chèn checklist DoD, script phát hiện KB cũ.
- **Impl-status:** Not started | **Review-status:** Pending

## Key Insights
- `okf/.git` = clone upstream GoogleCloudPlatform/knowledge-catalog → drift 2 chiều với repo cha (xác nhận: remote origin = upstream).
- 30 file KB Web Monocle đã populated ở `okf/` root; harness đã "declare" `project/docs/**` là OKF → 2 nhà cần hợp nhất về `okf/catalog/`.
- Frontmatter thật đã dùng `sources[].resource` + `generated:{by,at}` + `sources_last_checked` → đã có nền provenance, chỉ cần chuẩn hoá.
- KHÔNG có `AGENTS.md`/`CONTEXT_RULES.md` ở root (harness H1 chưa tạo) → GĐ1 phải standalone, không lệ thuộc.

## Requirements
- R1: Kill nested `.git`, tách vendored tooling khỏi content (Quyết định A).
- R2: KB canonical DUY NHẤT tại `okf/catalog/` (Quyết định B), không tạo `knowledge/`.
- R3: `okf/MAPPING.md` — bản đồ module↔file, KHÔNG trùng tên harness CONTEXT_RULES.
- R4: Checklist "OKF Updates Required" chèn vào story template + Definition of Done.
- R5: Script Python `okf-check outdated` báo KB cũ (so mtime code với `sources_last_checked`).
- R6: Backward-compatible: 0 thay đổi tới 23 YAML, store.py, schemas JSON.

## Architecture
```
okf/
  index.md              # điểm vào duy nhất (đã có, cập nhật link)
  MAPPING.md            # NEW: module↔file map (R3)
  log.md                # changelog (đã có)
  _vendor/              # NEW: reference-only, Apache-2.0
    VENDOR.md           # commit-hash upstream đã pin
    document.py, viewer/, SPEC.md
  catalog/              # NEW canonical home (dời từ okf/ root)
    datasets/ tables/ pipelines/ metrics/ playbooks/ references/ configurations/
scripts/
  okf_check.py          # NEW: CLI tối giản `okf-check outdated` (stdlib + python-frontmatter)
```
- `okf-check outdated` (GĐ1) = script đơn, KHÔNG phải package đầy đủ (đó là GĐ2). Chỉ: parse frontmatter → với mỗi `sources[].resource` là file code → so `git log -1 --format=%cI <file>` (hoặc mtime) với `sources_last_checked` → in bảng stale.
- Fallback không-git: dùng `os.path.getmtime`.

## Related code files (real paths)
- `okf/` (toàn bộ, restructure) · `okf/.git` (XOÁ) · `okf/index.md` · `okf/log.md`
- `okf/okf/src/reference_agent/bundle/document.py` → `okf/_vendor/document.py`
- `okf/okf/src/reference_agent/viewer/` → `okf/_vendor/viewer/`
- `project/src/db/store.py` (chỉ đọc, mục tiêu drift GĐ2)
- `project/config/domains/*.yaml` (23 file, chỉ đọc)
- `docs/templates/story.md` (chèn checklist — harness Phase-02 planned; nếu chưa có, tạo stub)
- `project/docs/others/decisions.md` (ADR-lite hiện có → link tới)
- `scripts/okf_check.py` (NEW)

## Implementation Steps
1. **Backup + pin:** `git -C okf rev-parse HEAD` → ghi `okf/_vendor/VENDOR.md`. Backup `okf/` ra ngoài repo.
2. **Kill nested git:** xoá `okf/.git`, `okf/.gitignore` upstream. `git add okf/` ở repo cha.
3. **Vendor tách:** tạo `okf/_vendor/`, chuyển `document.py`+`viewer/`+`SPEC.md`+LICENSE. Xoá `okf/okf/` (còn lại), `okf/toolbox/`, `okf/samples/`, boilerplate Google.
4. **Dời content:** `okf/{datasets,tables,...}` → `okf/catalog/{...}`. Sửa relative links nội bộ (đa số `../pipelines/x.md` giữ nguyên vì cùng chuyển). Kiểm link gãy.
5. **Viết `okf/MAPPING.md`:** bảng module code → OKF concept file (vd `src/db/store.py`→`catalog/tables/articles.md`; `config/domains/*`→`catalog/configurations/domain_sources.md`).
6. **Cập nhật `okf/index.md`:** trỏ vào `catalog/`; ghi rõ "canonical home = okf/catalog/; project/docs = sources".
7. **Checklist DoD (R4):** chèn block "OKF Updates Required" (từ researcher-02 §4) vào `docs/templates/story.md` + mục Definition of Done. Nếu template chưa tồn tại (harness chưa build) → tạo stub tối giản, đánh dấu "harness sẽ mở rộng".
8. **`scripts/okf_check.py`:** implement `outdated` subcommand (argparse + python-frontmatter). Output: bảng `file | last_checked | code_mtime | STALE?`.
9. **Chuẩn hoá `sources_last_checked`:** đảm bảo mọi concept có field này (thêm nếu thiếu).
10. **Chạy `okf-check outdated`** → clean run (fix concept stale thủ công).

## Todo list
- [ ] Pin upstream hash → VENDOR.md
- [ ] Xoá `okf/.git` + boilerplate
- [ ] Tạo `okf/_vendor/` (document.py, viewer, SPEC)
- [ ] Dời content → `okf/catalog/`, fix links
- [ ] Viết `okf/MAPPING.md`
- [ ] Cập nhật `okf/index.md`
- [ ] Chèn checklist OKF vào story template + DoD
- [ ] Viết `scripts/okf_check.py outdated`
- [ ] Chuẩn hoá `sources_last_checked` toàn bộ concept
- [ ] Stale-report chạy clean

## Success Criteria (KPI/DoD)
- **KPI:** 100% story hoàn thành có OKF update tương ứng (checklist tick).
- **DoD:** (a) `okf/.git` không còn; (b) 0 file KB còn ở `okf/` root (đã dời `catalog/`); (c) `okf/MAPPING.md` phủ 100% concept; (d) `okf-check outdated` chạy clean; (e) 23 YAML + store.py + schemas JSON KHÔNG đổi (git diff = 0 trên các path đó).

## Risk Assessment
- Xoá `.git` mất history → mitigate: VENDOR.md + backup ngoài repo.
- Dời folder gãy relative link → mitigate: grep `](\.\./` sau khi dời; script kiểm link.
- Template chưa tồn tại (harness H1 chưa build) → mitigate: tạo stub, không block.

## Security Considerations
- LICENSE Apache-2.0 phải theo file vendored (giữ trong `_vendor/`).
- `secrets.yaml` gitignored — OKF `configurations/settings.md` mô tả cấu trúc, KHÔNG chứa secret thật.

## Next steps
→ GĐ2: nâng `scripts/okf_check.py` thành package `okftools/` đầy đủ (parser/model/graph/cli) + drift validate + pre-commit.
