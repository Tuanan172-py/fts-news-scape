# Phase 01 — Input Compile (xlsx → yaml) + Template + Enable/Disable

## Context links
- Parent: [plan.md](plan.md) · Scout: [scout-02-entities-xlsx.md](scout/scout-02-entities-xlsx.md)
- Reuse: `project/src/agent/entities.py` (EntityRegistry.select, load_registry lru_cache)
- Emits target: `project/config/entities/users/<name>.yaml`

## Overview
- **Date:** 2026-08-18 · **Priority:** P0 (blocks all) · **Impl status:** ⬜ · **Review:** ⬜
- Chuyển input người-dùng (Excel) → yaml config máy đọc, tự sinh 1 file/user, báo entity không map được.

## Key Insights
- `EntityRegistry.select(doc)` đã làm toàn bộ việc map + báo unknown → compile chỉ cần dựng `doc` từ xlsx rồi gọi select() để VALIDATE (không cần tự map).
- `load_registry()` bị `@lru_cache` → sau khi ghi yaml phải `load_registry.cache_clear()` để nạp lại subscription.
- pandas + openpyxl đã có sẵn. build_entities.py đã dùng `pandas.read_excel`.
- Không đưa `enabled` vào yaml entity (giữ yaml thuần entity). Enable/disable = file trung tâm `users/input/manifest.yaml` (CHỐT với user) — KHÔNG dùng ô xlsx.

## Requirements
1. Template xlsx cho user nhập (đơn giản, có dropdown gợi ý, hướng dẫn tiếng Việt).
2. Script compile: quét `users/input/*/entities.xlsx` → yaml `config/entities/users/<name>.yaml`.
3. Báo cáo unknown (entity nhập sai) trả lại cho user, không làm hỏng compile.
4. Xác định user enabled/disabled.
5. Idempotent: chạy lại ghi đè yaml, không tạo rác.

## Architecture
### xlsx template schema (`users/template/entities_template.xlsx`)
- Sheet `entities`: cột dọc, mỗi cột 1 nhóm, 1 giá trị/dòng:
  `tickers | etfs | indices | exchanges | industries | sectors | entities`
  (khớp đúng key của `EntityRegistry.select`).
- Sheet `meta`: `user` (tên, mặc định = tên folder), `note`. (enabled KHÔNG ở đây — dùng manifest.yaml).
- Sheet ẩn `_lookup`: danh sách hợp lệ (codes/industries/sectors) copy từ `data/entities/entities.xlsx`
  để gắn Data Validation (dropdown). Sheet `huong_dan`: chú thích cách nhập.
- Generator: `scripts/make_user_template.py` — đọc entities.xlsx (Securities/Industries/Sectors_FPA/
  Indices/Exchanges) → dựng `_lookup` + dropdown bằng openpyxl `DataValidation`.

### compile script (`scripts/compile_users.py`)
```
for dir in users/input/*/ (bỏ _*):
    xlsx = dir/entities.xlsx
    doc  = read_entities_sheet(xlsx)   # pandas.read_excel sheet 'entities' → {key: [nonempty cells]}
    meta = read_meta_sheet(xlsx)       # user, enabled
    ids, unknown = registry.select(doc)
    write yaml -> config/entities/users/<name>.yaml  (header: AUTO-GENERATED; keys = doc đã strip rỗng)
    if unknown: write users/input/<name>/_unknown.txt  (dòng: "<nhóm>: <giá trị> — không tìm thấy")
# enabled đọc từ users/input/manifest.yaml (P4 dùng); compile bỏ qua user không có trong manifest? -> compile TẤT CẢ folder, manifest chỉ lọc lúc chạy output
load_registry.cache_clear()
```
### manifest.yaml (`users/input/manifest.yaml`)
```yaml
# Bật/tắt user cho workflow. Thiếu tên = coi như enabled (mặc định an toàn) HOẶC bắt buộc khai báo — CHỐT: default enabled nếu vắng.
users:
  AnPT: true
  A: false
```
- `doc` chỉ giữ nhóm có giá trị (tránh key rỗng). Trim/upper mã ticker; giữ nguyên tên ngành.
- Yaml giữ nguyên format hiện có (khớp AnPT.yaml) để `_load_subscriptions` đọc được ngay.

## Related code files
- NEW `project/scripts/make_user_template.py`, `project/scripts/compile_users.py`
- NEW helper `project/src/users/compile.py` (logic parse+emit, để test unit)
- READ `project/src/agent/entities.py`, `project/data/entities/entities.xlsx`
- WRITE `project/config/entities/users/<name>.yaml`, `users/template/entities_template.xlsx`

## Implementation Steps
1. `src/users/compile.py`: `read_user_xlsx(path)->(doc, meta)`, `compile_user(name, xlsx, registry)->(yaml_path, unknown)`, `compile_all(input_root, registry)->list[result]`.
2. `scripts/compile_users.py`: CLI wrapper (`--input-root users/input`, `--all`/`--users`), gọi compile_all, in summary, `cache_clear()`.
3. `scripts/make_user_template.py`: sinh template + copy sang mỗi folder mới thiếu file.
4. Seed `users/input/AnPT/entities.xlsx` từ `config/entities/users/AnPT.yaml` hiện có (giữ dữ liệu mẫu).

## Todo list
- [ ] compile.py (parse xlsx → doc/meta)
- [ ] compile.py (select + emit yaml + unknown report)
- [ ] compile_users.py CLI + cache_clear
- [ ] make_user_template.py (dropdowns từ entities.xlsx)
- [ ] Seed AnPT template

## Success Criteria
- Chạy `python scripts/compile_users.py --all` → sinh/ghi đè `config/entities/users/AnPT.yaml` khớp entity mẫu.
- Entity nhập sai → liệt kê trong `_unknown.txt`, compile vẫn xong.
- Folder `_disabled/` bị bỏ qua; `enabled=FALSE` được ghi nhận.

## Risk Assessment
- xlsx dropdown lớn (1981 ticker) → sheet `_lookup` nặng; chấp nhận, đóng băng cột.
- Tên ngành/sector sai chính tả dấu → dựa `_fold` của registry (đã bỏ dấu) nên khá bền.

## Security Considerations
- Chỉ đọc xlsx nội bộ; không exec macro. Dùng `data_only`/`read_only` khi mở openpyxl.

## Next steps
→ Phase 02 dùng subscriptions đã compile để lọc output.

## Unresolved
- Vị trí `enabled`: ô meta xlsx (đề xuất) vs manifest riêng — cần user chốt (Q4 plan.md).
