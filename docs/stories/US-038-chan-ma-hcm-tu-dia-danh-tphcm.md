# US-038 — Chặn mã HCM bị gán từ địa danh TP.HCM ở tầng cào

- **Status:** done
- **Lane:** normal
- **Parent / Epic:** none
- **Intake date:** 2026-11-12
- **Depends On:** none

## Product Contract
Cột `articles.symbols` không gán mã chứng khoán HCM (HSC) cho bài nói về địa bàn TP.HCM. Bài về HSC vẫn được gán HCM.

## Acceptance Criteria
- [x] `tag_tickers` bỏ qua mã nằm trong cụm địa danh: `TP.HCM`, `TP HCM`, `Tp. HCM`, `Thành phố HCM`, `UBND HCM`, `khu vực HCM`, `HCM City`, `HCMC`
- [x] Bộ khớp entity (`src/agent/entities.py`) dùng chung guard `is_location_context` thay cho regex riêng
- [x] Script `scripts/retag_location_symbols.py` dọn dữ liệu cũ, mặc định chạy thử, ghi nhật ký hoàn tác CSV khi `--apply`
- [x] Chạy thử trên DB vận hành: 1.144 bài gỡ HCM, 191 bài HSC giữ HCM, không mã nào khác bị ảnh hưởng
- [x] Chạy `--apply` 2026-11-12 15:33: 1.145 bài; daemon khởi động lại 15:39 từ checkout có mã mới

## Design Notes
Nguồn của 1.102+ bài HCM trong báo cáo là cột `articles.symbols` do `src/core/tickers.py::tag_tickers` gán lúc cào (baodautu, cafef, rss_generic, tnck, vietstock, vneconomy). Hàm này chỉ có stoplist, không có guard ngữ cảnh. `entities.py` đã có guard trái nhưng không được tầng cào dùng. Lớp nhận diện của mô hình (`l1_outputs`) chỉ có 214 bài TICKER:HCM, không phải nguồn chính.

## Validation
| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `python -m pytest tests/test_tickers.py` | passed | 7 test đạt (2 test mới) |
| Regression | `python -m pytest tests/` | baseline | 8 failed + 18 errors giống hệt HEAD trước thay đổi (thiếu `data/entities/entities.json` sau US-037) |
