# Web Monocle — Project Charter

## 1. Tổng quan dự án

**Tên dự án:** Web Monocle
**Mục đích:** Hệ thống giám sát nội dung web đa nguồn (RSS, API, HTML scraping) — tự động thu thập, xử lý, lưu trữ và thông báo tin tức liên quan đến lĩnh vực tài chính và giao dịch VN30F1M.

**Vai trò:** Hệ thống infrastructure phụ trợ, chạy song song với trading pipeline hiện tại, không ảnh hưởng đến luồng giao dịch chính.

---

## 2. Infrastructure & Môi trường

### 2.1 Môi trường chạy

| Thành phần | Môi trường | Ghi chú |
|-----------|-----------|---------|
| **Python collector** | WSL (Ubuntu) | Chạy cùng máy với Hermes Agent |
| **Script cron inject** | Hermes scheduler | Dùng `--workdir` trỏ vào project |
| **Database primary** | SQLite | local, portable, không cần server |
| **Database analytics** | ClickHouse (orderflow) | Đã có sẵn, dùng batch sync |
| **Storage raw files** | local filesystem | `data/raw/{domain}/{date}/` |
| **Notification** | Telegram | Hermes send_message → chat An |
| **Scheduler** | Hermes cron | Cron job per collection |

### 2.2 Infrastructure constraints

- **Không thêm server mới** — mọi thứ chạy trên máy hiện tại (T7920, WSL)
- **Không thêm database service mới** — chỉ dùng SQLite + ClickHouse có sẵn. Không PostgreSQL, không Elasticsearch
- **Không phụ thuộc cloud dịch vụ bên ngoài** — ngoại trừ HTTP requests đến RSS feeds và article URLs
- **Hermes Agent là single point of orchestration** — cron, notification, skill management đều qua Hermes

### 2.3 Network requirements

- Outbound HTTPS đến các RSS feed URLs
- Outbound HTTPS đến article URLs (khi extract full content)
- Không cần inbound ports
- Rate limit tự quản (3s delay giữa các request đến cùng domain)

### 2.4 Storage estimates

| Item | Daily volume | Monthly | Annual |
|------|-------------|---------|--------|
| Articles (full content) | ~200-500 articles | 6K-15K | 73K-180K |
| Raw HTML cached | ~50-100 MB | 1.5-3 GB | 18-36 GB |
| SQLite DB | ~5-10 MB | 150-300 MB | 1.8-3.6 GB |
| ClickHouse (nếu sync) | ~2-5 MB (compressed) | 60-150 MB | 720 MB-1.8 GB |

→ SQLite hoàn toàn đủ cho ít nhất 12 tháng trước khi cần cleanup.

---

## 3. Mục tiêu dự án (Project Goals)

### 3.1 Mục tiêu cốt lõi (Core)

| ID | Mục tiêu | Mô tả | Priority |
|----|---------|-------|----------|
| G-1 | **Thu thập tự động** | Hệ thống tự động fetch RSS từ các nguồn tin tài chính không cần can thiệp thủ công | P0 |
| G-2 | **Full content extraction** | Không chỉ lấy title/summary — lấy được toàn bộ nội dung bài viết | P0 |
| G-3 | **Deduplication chính xác** | Không gửi tin trùng (cùng bài từ nhiều nguồn) cho user | P0 |
| G-4 | **Notification kịp thời** | Tin mới liên quan VN30F1M/chứng khoán → gửi Telegram trong vòng 30 phút (cùng cycle cron) | P0 |
| G-5 | **Phân loại nội dung** | Article được gắn category (finance/trading/tech/cmt) để filter + route notification | P1 |
| G-6 | **Lưu trữ tra cứu được** | Articles lưu trong database, query được theo thời gian, category, từ khoá | P1 |

### 3.2 Mục tiêu mở rộng (Future)

| ID | Mục tiêu | Mô tả | Priority |
|----|---------|-------|----------|
| G-7 | **Entity extraction** | Trích xuất ticker (VN30F1M, VCB, SSI...), person, org từ article body | P2 |
| G-8 | **LLM summarization** | Tóm tắt article dài thành 2-3 câu bằng LLM trước khi gửi | P2 |
| G-9 | **Daily digest** | Gom các articles không urgent gửi 1 lần/ngày thay vì real-time | P2 |
| G-10 | **Multi-domain scraping** | Mở rộng từ RSS sang HTML scraping cho domain không có RSS | P2 |
| G-11 | **API endpoint collector** | Kết nối đến API internal của các trang tài chính (nếu reverse được) | P3 |
| G-12 | **Trend detection** | Phát hiện từ khoá/topic nổi lên trong khoảng thời gian | P3 |
| G-13 | **Vector search** | Semantic search qua articles đã lưu (dùng embedding) | P3 |

---

## 4. Định hướng kiến trúc (Architecture Direction)

### 4.1 Nguyên tắc thiết kế

| Nguyên tắc | Mô tả |
|-----------|-------|
| **KISS (Keep It Simple)** | Giải pháp đơn giản nhất hoạt động được → chọn nó trước. Không over-engineering |
| **Progressive enhancement** | Bắt đầu với RSS + SQLite. Thêm ClickHouse sync, LLM, API scraper sau nếu cần |
| **Config-driven** | Thêm nguồn tin mới = thêm vài dòng YAML. Không cần viết code mới |
| **Graceful degradation** | RSS feed chết → log + skip, không crash pipeline. Extract full article fail → fallback về summary |
| **Idempotent operations** | Chạy collector 2 lần với cùng dữ liệu → kết quả giống nhau (dedup handles) |
| **Observable by default** | Mọi collection cycle đều log ra stdout → Hermes agent visible trong cron output |
| **Zero side-effect on trading** | Web Monocle không được ảnh hưởng đến CPU/memory/network của trading pipeline chính |

### 4.2 Chiến lược xử lý dữ liệu

```
Phase 1 (MVP):    RSS → Dedup → Extract → Classify → SQLite → Telegram
                    ↑ rule-based      ↑ keyword    ↑ Hermes cron inject pattern
             
Phase 2 (Tuning): + ClickHouse sync (batch, every 1h)
                  + LLM summarization (cho articles > 500 chars)
                  + Notification rules engine (config YAML)

Phase 3 (Scale):  + HTML scraper cho domain không có RSS
                  + API reverse engineering
                  + Daily digest (gom non-urgent articles)
```

### 4.3 Data flow ràng buộc

```
[Cron tick] → [Script] → [stdout] → [Hermes agent] → [LLM decide notification] → [Telegram]
     ↑             ↑                                                       
     │        Chạy collection,                                          
     │        output = danh sách articles mới + metadata                 
     │                                                                  
     └─── 15 phút 1 lần (cấu hình được)                                
```

→ Script KHÔNG tự gửi Telegram. Script chỉ output data. Hermes agent đọc output và quyết định gửi gì.

---

## 5. Ràng buộc kế hoạch (Planning Constraints)

### 5.1 Ràng buộc kỹ thuật

| ID | Ràng buộc | Mô tả |
|----|----------|-------|
| C-01 | **Single-machine deployment** | Mọi component chạy trên 1 máy (T7920, WSL). Không cluster, không distributed |
| C-02 | **Hermes dependency** | Scheduling, notification, skill management đều qua Hermes Agent. Không dùng cron system riêng (systemd/crontab) |
| C-03 | **Python 3.10+** | Code viết bằng Python, chạy trên WSL Python venv |
| C-04 | **No new database daemons** | Chỉ SQLite (file-based). ClickHouse đã có, không cài thêm PostgreSQL/ES/Mongo |
| C-05 | **No cloud storage** | Không S3, không GCS, không cloud DB. Local storage duy nhất |
| C-06 | **Rate limiting mandatory** | Tất cả HTTP requests phải có delay giữa các request đến cùng domain (default 3s) |
| C-07 | **Network timeout guard** | Mọi external request có timeout ≤ 30s. Không treo vô hạn |
| C-08 | **No sensitive data in code** | API keys (nếu có) lưu trong .env file, không commit |
| C-09 | **graceful shutdown** | Script bị kill giữa chừng → không corrupt dedup cache, không corrupt DB |

### 5.2 Ràng buộc vận hành

| ID | Ràng buộc | Mô tả |
|----|----------|-------|
| O-01 | **Cron không overlap** | Nếu collection chạy 20 phút (do rate limit) → cron 15 phút không được chồng lấn. Dùng Hermes cron single-instance |
| O-02 | **Disk space monitoring** | data/ tối đa 10GB. Alert khi > 8GB. Cleanup script chạy monthly |
| O-03 | **Dedup cache bảo toàn** | Không xoá dedup_cache.json trừ khi cố tình reset. Nếu mất → trùng articles sẽ gửi lại |
| O-04 | **Notification không spam** | Cùng 1 article không gửi quá 1 lần. Dedup handles. Nếu notification rule sai → sửa config, không cần code |
| O-05 | **Maintenance window** | Thay đổi selector/format → test với 1 entry trước khi deploy vào cron. Không sửa trực tiếp trên production cron |

### 5.3 Ràng buộc phát triển

| ID | Ràng buộc | Mô tả |
|----|----------|-------|
| D-01 | **Incremental delivery** | Mỗi phase phải là 1 working system. Phase 1 (MVP) dùng được ngay, không cần đợi phase 2 |
| D-02 | **Test trước khi deploy** | Mỗi module có test (ít nhất happy path + 1 edge case). Chạy `python tests/test_*.py` pass hết mới deploy |
| D-03 | **Config trước code** | Thêm nguồn dữ liệu mới → config YAML trước. Nếu config không đủ → mới viết code mới |
| D-04 | **Documentation song song** | Mỗi feature hoàn thành → cập nhật docs/ và skills/ tương ứng. Không để nợ docs |
| D-05 | **Skill-first Hermes integration** | Mọi workflow có skill file tương ứng. Cron deploy qua skill, không qua ad-hoc command |
| D-06 | **Commit message convention** | `web-monocle: <module>: <what changed>` — ví dụ `web-monocle: rss/collector: add Atom feed support` |

### 5.4 Ràng buộc thời gian

| ID | Ràng buộc | Mô tả |
|----|----------|-------|
| T-01 | **Phase 1 MVP** | RSS + SQLite + Telegram notification — ưu tiên hoàn thành trước khi mở rộng |
| T-02 | **No batching delay** | Notification gửi trong cùng cron cycle (15 phút). Không cache chờ batch |
| T-03 | **ClickHouse sync** | Là optional phase. Không block MVP. Chỉ implement khi SQLite đủ chậm hoặc cần CH query |

---

## 6. Phân kỳ công việc (Work Breakdown Structure)

### Phase 1 — MVP (hiện tại đã có code skeleton)

```
[ ] Setup project structure           → DONE (24 files)
[ ] Config collections.yaml           → Mẫu (cần chỉnh feeds thật)
[ ] Install dependencies             → pip install -r requirements.txt
[ ] Test: fetch 1 RSS feed thật      → python -c "from src.rss.collector import fetch_feed; print(len(fetch_feed('https://vnexpress.net/rss/kinh-doanh.rss')))"
[ ] Test: extract 1 article thật     → python -c "from src.processor.extractor import extract_content; print(extract_content('https://vnexpress.net/...'))"
[ ] Test: pipeline end-to-end        → python src/run_collection.py financial_vn
[ ] Deploy cron                      → bash scripts/deploy_crons.sh
[ ] Verify: notification nhận được   → Chờ cron tick → check Telegram
```

### Phase 2 — Nâng cao

```
[ ] ClickHouse batch sync (1h/lần)
[ ] LLM summarization cho articles dài
[ ] Notification rules engine (từ config YAML)
[ ] Entity extraction (ticker, person, org)
[ ] Daily digest format
```

### Phase 3 — Mở rộng

```
[ ] HTML scraper cho domain không có RSS
[ ] API endpoint collector
[ ] Trend detection
[ ] Vector search
```

---

## 7. Success Criteria

| Tiêu chí | Measure | Target |
|----------|---------|--------|
| **Coverage** | Số nguồn RSS hoạt động | ≥ 3 nguồn tài chính VN |
| **Latency** | Thời gian từ khi article publish → notification | ≤ 30 phút (2 cron cycles) |
| **Accuracy** | Articles được classify đúng category | ≥ 80% (rule-based) |
| **Dedup** | Articles trùng không gửi lại | 100% (URL hash) |
| **False positive** | Notification không liên quan gửi nhầm | ≤ 5% (có thể tuning rules) |
| **Uptime** | Cron job chạy đúng lịch | ≥ 99% (không tính lỗi network) |

---

## 8. Risk & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-----------|--------|------------|
| RSS feed thay đổi URL/chết | Cao | Trung bình | Alert khi feed 404 > 3 lần. Dự phòng domain scraper |
| Domain thay đổi HTML layout | Cao | Thấp | Generic extractor (trafilatura) tự điều chỉnh. Chỉ ảnh hưởng nếu dùng selector custom |
| Rate limit / bị block IP | Trung bình | Cao | User-agent rotation, delay 3s, exponential backoff |
| Dedup cache corrupt | Thấp | Cao | Backup định kỳ, có thể rebuild từ DB |
| Cron overlap | Thấp | Trung bình | Hermes cron single-instance. Nếu script chạy quá 15 phút → skip tick |
| ClickHouse unavailable | Trung bình | Thấp | Graceful fallback về SQLite. Không ảnh hưởng notification flow |
| LLM summarization cost | Trung bình | Thấp | Chỉ summarize articles > 500 chars. Giới hạn 1 article/cron cycle |

---

## 9. Stakeholders & Communication

| Stakeholder | Vai trò | Nhu cầu thông tin | Tần suất |
|-------------|---------|-------------------|----------|
| **An Pham** | Owner, user duy nhất | Notification tin liên quan VN30F1M | Real-time (15 phút) |
| **An Pham** | Maintainer | Health check logs, feed alive/dead status | Daily |
| **Hermes Agent** | Orchestrator | Cron output → quyết định notify | Mỗi tick |
