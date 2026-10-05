# Technical Decision Records

> **2026-07-24:** TDR-001..003 giữ nguyên giá trị; TDR-004..006 (SQLite WAL
> single-writer, standalone, sync requests) xem `docs/architecture.md`.
> TDR-003 cập nhật: fuzzy layer dùng **rapidfuzz token_set_ratio ≥90** (thay
> difflib), window 48h, chỉ so cross-domain — implemented `src/db/dedup.py`.

## TDR-001: RSS làm primary data source

**Context:** Cần monitor nhiều nguồn tin tài chính VN, mỗi nguồn có cấu trúc khác nhau.

**Decision:** RSS là primary source. Fallback về HTML scraping khi:
1. Domain không có RSS feed
2. RSS chỉ có title, không có description → scrape full article

**Consequences:**
- Setup nhanh (5 phút / feed)
- Maintenance thấp
- Cần thêm lớp generic extractor cho full content

---

## TDR-002: Generic extractor thay vì selector per domain

**Context:** RSS entries trỏ đến nhiều domain khác nhau, không thể viết CSS selector riêng.

**Decision:** Dùng `trafilatura` làm extractor chính. Nếu domain quan trọng và extractor cho kết quả kém → viết selector riêng cho domain đó.

**Consequences:**
- 85-90% accuracy — đủ cho monitoring
- Không cần maintain selector cho từng domain
- Domain đặc thù (bảng biểu, số liệu) cần xử lý riêng

---

## TDR-003: Dedup 2 lớp

**Context:** 1 article có thể xuất hiện ở nhiều feeds, nhiều domain.

**Decision:** URL hash (SHA-256) + Title fuzzy match (difflib ratio > 0.85)

**Consequences:**
- URL hash xử lý 95% trường hợp
- Fuzzy match bắt articles cùng nội dung khác URL
- Chi phí tính toán thấp
