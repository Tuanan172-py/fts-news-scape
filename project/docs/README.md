# Tài liệu Web Monocle

Bộ tài liệu chuyên sâu cho hệ thu thập tin tức thị trường chứng khoán VN. Cập nhật 2026-07-26
(Phase 1 + 2 hoàn thành, 23 domain, 112 test).

## Đọc theo đối tượng

| Bạn là… | Bắt đầu ở |
|---|---|
| Mới, cần bức tranh lớn | [design/01-system-overview.md](design/01-system-overview.md) |
| Kiến trúc sư / tech lead | thư mục [design/](design/) + [decisions.md](decisions.md) |
| Dev sắp sửa code | [dev/01-codebase-guide.md](dev/01-codebase-guide.md) |
| Muốn thêm nguồn tin | [dev/03-adding-a-source.md](dev/03-adding-a-source.md) |
| Làm việc trên 2 máy (dev + vận hành) | [dev/07-two-machine-workflow.md](dev/07-two-machine-workflow.md) |
| Vận hành / trực hệ thống | [operations/deployment.md](operations/deployment.md) + [operations/troubleshooting.md](operations/troubleshooting.md) |
| Tìm hiểu 1 domain cụ thể | [domains/README.md](domains/README.md) |

## Cấu trúc

### 🎯 design/ — Thiết kế (vì sao & luồng)
- [01-system-overview.md](design/01-system-overview.md) — tổng quan, triết lý, sơ đồ khối
- [02-execution-flow.md](design/02-execution-flow.md) — luồng thực thi từng bước (file:line)
- [03-source-strategy.md](design/03-source-strategy.md) — chiến lược nguồn, xử encoding/date/dedup/filter
- [04-sentiment-classification.md](design/04-sentiment-classification.md) — sentiment & phân loại rule-based
- [05-notification-coverage.md](design/05-notification-coverage.md) — notify: phủ toàn thị trường (sources/has_symbol/keyword), 98% coverage
- [13-per-user-output-workflow.md](design/13-per-user-output-workflow.md) — quy trình end-to-end lớp NGƯỜI DÙNG: input Excel → compile → L1/agent → CSV output per user

### 🔧 dev/ — Cho lập trình viên (code chạy thế nào)
- [01-codebase-guide.md](dev/01-codebase-guide.md) — cây thư mục, tầng, registry, HTTP client
- [02-data-model-and-db.md](dev/02-data-model-and-db.md) — Article, schema SQLite, DBWriter, dedup
- [03-adding-a-source.md](dev/03-adding-a-source.md) — thêm nguồn RSS/API (có checklist)
- [04-testing.md](dev/04-testing.md) — bản đồ 112 test, FakeHTTP, fixtures
- [05-known-issues.md](dev/05-known-issues.md) — vấn đề đã biết & nợ kỹ thuật
- [06-raw-html-capture-guide.md](dev/06-raw-html-capture-guide.md) — hướng dẫn capture Bronze byte-exact
- [07-two-machine-workflow.md](dev/07-two-machine-workflow.md) — quy trình 2 máy: dev qua GitHub + vận hành trên OneDrive

### 🌐 domains/ — Chi tiết từng nguồn
- [README.md](domains/README.md) — ma trận 23 domain + watchlist + settings
- [api-scrapers.md](domains/api-scrapers.md) — cafef, fireant, tnck, vndirect
- [exchange-layer0.md](domains/exchange-layer0.md) — hose, hnx (sàn chính thống)
- [vn-rss.md](domains/vn-rss.md) — 11 báo VN
- [intl-rss.md](domains/intl-rss.md) — 5 báo tài chính quốc tế

### 🚀 operations/ — Triển khai & sự cố
- [deployment.md](operations/deployment.md) — cài, chạy, monitor, backup
- [troubleshooting.md](operations/troubleshooting.md) — triệu chứng → xử lý
- [db-health-queries.md](operations/db-health-queries.md) — query DB kiểm tra nhanh trạng thái scrape (dashboard `scripts/db_status.py` + SQL thô)
- [agent-prompting-guide.md](operations/agent-prompting-guide.md) — prompt mồi + context agent cần đọc + tiêu chí nghiệm thu (DoD) + vòng lặp tới khi hoàn thành
- [monocle-db-handbook.md](operations/monocle-db-handbook.md) — sổ tay vận hành DB hàng ngày: schema, cookbook query theo tình huống, sự cố, backup/bảo trì (`scripts/dbq.py`)

## Tài liệu nền (có sẵn)
- [architecture.md](architecture.md) — kiến trúc + TDR (bản gốc Phase 1)
- [decisions.md](decisions.md) — technical decision records
- [runbook.md](runbook.md) — quy trình vận hành
- [skills/](skills/) — quirk chi tiết per-source (cafef, tnck, fireant, rss-sources)
- [phase1-report.md](phase1-report.md), [rss-reference.md](rss-reference.md)

## Trạng thái nhanh
- 23 domain: 22 enabled + 1 disabled (baodautu). vi=17, en=6.
- DB: SQLite WAL 1 file `data/monocle.db` (~550MB).
- Sentiment: rule-based VN (lexicon 316 term); EN → neutral.
- Test: 112 passing.
- **Lưu ý vận hành:** chỉ chạy 1 scheduler (xem known-issues §1.1).
