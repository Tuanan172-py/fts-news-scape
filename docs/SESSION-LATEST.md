# Bàn giao Phiên Vận Hành (Session Handoff)

**Thời điểm:** 2026-10-20 (GMT+7)  
**Nhánh:** dev/us038 | **Nhiệm vụ:** US-044 — Bộ kỹ năng theo use case analyst cho plugin `fpts-market-intel`

Phiên trước (US-038: di chuyển Lakehouse sang sandbox `FRA_DataIngestion`, ADR-0025, plugin bản 1.0.0) xem trong lịch sử git của tệp này.

---

## 1. Định hướng đã chốt (brainstorm cùng operator)

Mọi kỹ năng dùng chung khuôn **Đối tượng (mã / ngành / chủ đề) + Khoảng thời gian + Câu hỏi**. DuckDB lọc, đếm, so mức nền (0 token); LLM chỉ diễn giải gói bằng chứng có trích dẫn.

| Team | Kỹ năng |
|---|---|
| Cơ bản | `news-ticker-timeline`, `news-catalyst-tracker`, `news-sector-impact` (+ `news-ticker-screener`) |
| Thị trường / Kỹ thuật | `news-buzz-radar`, `news-sentiment-pulse` (đổi tên từ `news-sector-pulse`), `news-price-explainer` |
| Vĩ mô / Địa chính trị | `news-macro-timeline`, `news-theme-trend`, `news-geo-link` |
| Morning | `news-daily-brief` ba tầng |
| Quant | `news-lakehouse-explorer` |

## 2. Thay đổi kỹ thuật (plugin 1.1.0)

- `tools/lakehouse_client.py`: view `articles` (`pub_date`, `story_key`, `sent_score`, `is_hot`) và `article_entities` (hợp nhất `entities` + `symbols`); bù cột thiếu khi lệch schema; lens mới `timeline`, `window`, `buzz`, `pulse`, `themes`, `cooccur`, `brief`, `lookup`, `themes-list`; sửa lỗi JSON hoá cột danh sách của lệnh `query`; chặn thêm `COPY/ATTACH/EXPORT/INSTALL/LOAD`.
- `config/themes.json`: 20 chủ đề (vĩ mô, địa chính trị, câu chuyện đầu tư, hàng hoá) định nghĩa bằng mã thực thể + từ khoá, analyst tự chỉnh.
- `rules/AGENTS.md`: thêm quy tắc tách **[Đo lường] / [Diễn giải]** và khai báo mức nền/độ phủ.
- Tri thức: FACT-lakehouse-symbols-column-is-sparse-filter-tickers-by (`symbols` chỉ có ở ~8% bài, lọc mã phải qua `entities`).

## 3. Kiểm chứng

- `pytest project/tests/test_plugin_lakehouse_client.py project/tests/test_plugin_manifest.py`: **23/23 PASS**.
- Toàn bộ `project/tests`: 953 PASS, **3 FAIL ngoài phạm vi plugin** (có từ trước): `test_code_first_guard::test_published_mentions_skip_code_first` (import `_build_parquet` không còn trong `src.export.publisher`), `test_daily_reporter::test_daily_reporter_metrics`, `test_ops_council_fixes::test_b2_sensor_does_not_count_reserved_articles`.
- Mọi lens đã chạy thật trên sandbox (4 ngày dữ liệu 16–19/10).

## 4. Việc tiếp theo

1. Operator đẩy toàn bộ lịch sử tin lên sandbox; sau đó chạy lại `buzz`, `pulse`, `themes` để kiểm tra mức nền đủ 20 phiên / 90 ngày.
2. Cài lại plugin cho analyst: `python scripts/install_market_intel_plugin.py`.
3. Thu golden questions từ từng team để chấm chất lượng 4 kỹ năng khởi đầu (ticker-timeline, buzz-radar, macro-timeline, daily-brief).
4. Sửa 3 test đỏ ngoài phạm vi (story riêng).
