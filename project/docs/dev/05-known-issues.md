# Dev — Vấn đề đã biết & nợ kỹ thuật

Cập nhật: 2026-10-22 · Đối tượng: dev/maintainer. Ghi trung thực trạng thái hiện tại.

## 1. Vận hành

### 1.1 Nhiều scheduler chạy song song (đã chặn)
Từng phát hiện 2 tiến trình cào tin chạy đồng thời → gấp đôi lưu lượng tới các báo. Nay
`capture.lock` (`src/core/proclock.py`) cộng khoá `scheduler` trong `pipeline_state` khiến
morninger, `src.orchestrator` và `--once` từ chối khởi động khi tiến trình khác đang giữ khoá.
Xem [../operations/troubleshooting.md](../operations/troubleshooting.md).

### 1.2 DB phình không giới hạn
`articles` và `scraper_metrics` (append-only) không có retention/rotation. `<DATA_ROOT>/monocle.db`
~550MB khi đo 2026-07-26. Chưa có job xoá bài cũ / gộp metrics.
→ **Đề xuất:** thêm script prune theo `fetched_at` + `VACUUM` định kỳ.

### 1.3 Thời gian cycle so với nhịp capture 10 phút
Đo 2026-09-17 với 8 nguồn bật: một lượt job capture của morninger ≈ 7 phút (capture ~335s + backfill ≤90s),
nhịp `morninger.capture_interval_minutes` = 10 (`config/settings.yaml`). Bật thêm nguồn có thể đẩy tổng cycle-time vượt nhịp. `coalesce=True, max_instances=1` đảm bảo
không chồng cycle, nhưng nếu vượt thì tần suất thực giảm (bỏ tick).
→ **Đề xuất:** log tổng duration mỗi cycle; nếu tiệm cận, giảm số mã watchlist cho cafef/fireant
hoặc tăng interval.

## 2. Dữ liệu / chất lượng

### 2.1 Cột `articles.sentiment` không còn được điền
Engine sentiment rule-based đã xoá; capture không điền `articles.sentiment`. Sentiment phân tích nằm ở
`agent_outputs` (Article Lane). Cột còn trong `_COLUMNS` của `src/db/store.py` để tương thích.

### 2.2 baodautu: RSS hỏng vĩnh viễn ở server
Feed trả channel rỗng. Từ 2026-09-07 nguồn bật lại bằng scraper HTML listing riêng (`method: baodautu`,
`src/scrapers/baodautu.py`); xem [../design/03-source-strategy.md](../design/03-source-strategy.md).

### 2.3 vndirect là aggregator → trùng nội dung khác URL
vndirect trả link báo gốc nên tin có thể trùng với nguồn khác. Lọc mờ ở tầng cào đã gỡ (ADR 0013).
Trùng được cụm hoá sau Bronze (ADR 0016) và vẫn giữ nguyên trong `articles`.

## 3. Code / tài liệu

### 3.1 hose: method rss nhưng URL là JSON API
`config/domains/hose.yaml` `method: rss` nhưng feed là `api.hsx.vn/.../NewsByCateFeed/21`
(JSON-feed). Đã verify feedparser xử được 2026-07-25 nhưng **chưa có test cố định** → rủi ro
regression nếu feedparser/endpoint đổi. → **Đề xuất:** thêm fixture + test.

### 3.2 TDR-003 (rapidfuzz ≥90) không còn hiệu lực
Lọc mờ theo tiêu đề đã gỡ khỏi tầng cào theo ADR 0013 vì loại nhầm bài. Cụm hoá theo ADR 0016 thay thế.

### 3.3 Cấu hình `fuzzy_dedup` còn sót trong test
Một số test trong `tests/scrapers/` vẫn khai `fuzzy_dedup: False`. Khoá này không còn tác dụng và có thể xoá.

## 4. Bảo mật

- `config/secrets.yaml` (FireAnt token) **gitignored** — đã xác nhận `git check-ignore`. Không
  bao giờ commit/log giá trị token. Chỉ commit `secrets.yaml.example`.
- FireAnt token có thể hết hạn → 401 → scraper self-disable + ERROR log 1 lần. Cập nhật thủ công.

## 5. Ưu tiên xử lý (đề xuất)

| Ưu tiên | Việc |
|---|---|
| Trung | (1.2) Retention DB · (3.1) Test hose |
| Thấp | (1.3) Đo cycle-time · (3.3) Xoá `fuzzy_dedup` trong test |
