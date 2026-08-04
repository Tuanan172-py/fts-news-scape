# Dev — Vấn đề đã biết & nợ kỹ thuật

Cập nhật: 2026-07-26 · Đối tượng: dev/maintainer. Ghi trung thực trạng thái hiện tại.

## 1. Vận hành

### 1.1 Nhiều scheduler chạy song song (RỦI RO)
Từng phát hiện 2 tiến trình `python -m src.orchestrator` (không `--once`) chạy đồng thời →
mỗi tiến trình có rate-limit riêng → **gấp đôi lưu lượng** tới các báo (nguy cơ chặn IP),
tốn CPU/mạng. Dữ liệu **không hỏng** (WAL + INSERT OR IGNORE lo trùng), chỉ lãng phí + số
liệu heartbeat nhiễu (last-writer-wins).
→ **Khắc phục:** đảm bảo chỉ 1 scheduler. Xem [../operations/troubleshooting.md](../operations/troubleshooting.md).

### 1.2 DB phình không giới hạn
`articles` và `scraper_metrics` (append-only) không có retention/rotation. `data/monocle.db`
hiện ~550MB. Chưa có job xoá bài cũ / gộp metrics.
→ **Đề xuất:** thêm script prune theo `fetched_at` + `VACUUM` định kỳ.

### 1.3 Thời gian cycle chưa đo so với interval 15 phút
cafef/fireant chạy theo 30 mã watchlist (~1 request/mã + rate 3s ≈ 90s mỗi nguồn). Với đủ 22
domain, tổng cycle-time có thể tiến gần/vượt 15 phút. `coalesce=True, max_instances=1` đảm bảo
không chồng cycle, nhưng nếu vượt thì tần suất thực giảm (bỏ tick).
→ **Đề xuất:** log tổng duration mỗi cycle; nếu tiệm cận, giảm số mã watchlist cho cafef/fireant
hoặc tăng interval.

## 2. Dữ liệu / chất lượng

### 2.1 Bài CafeF cũ thiếu sentiment
~121 bài CafeF backfill **trước khi** wiring pipeline sentiment → cột `sentiment` rỗng. Bài mới
đã có. → **Khắc phục:** script backfill quét `sentiment IS NULL/''`, chạy `analyze` lại.

### 2.2 baodautu dormant (disabled)
`config/domains/baodautu.yaml` `enabled: false` — feed trả XML hợp lệ nhưng **0 `<item>`**
(verified nhiều UA/client). Giống NDH. Bật lại: đổi `enabled: true` khi feed hồi.

### 2.3 vndirect là aggregator → phụ thuộc fuzzy dedup
vndirect trả link báo gốc; tin trùng với nguồn khác chỉ được khử ở **lớp 2 fuzzy** (khác URL).
Nếu tắt `fuzzy_dedup` → xuất hiện trùng nội dung khác URL.

## 3. Code / tài liệu

### 3.1 hose: method rss nhưng URL là JSON API
`config/domains/hose.yaml` `method: rss` nhưng feed là `api.hsx.vn/.../NewsByCateFeed/21`
(JSON-feed). Đã verify feedparser xử được 2026-07-25 nhưng **chưa có test cố định** → rủi ro
regression nếu feedparser/endpoint đổi. → **Đề xuất:** thêm fixture + test.

### 3.2 Mâu thuẫn tài liệu TDR-003 (difflib vs rapidfuzz)
`docs/decisions.md` TDR-003: header nói rapidfuzz ≥90 nhưng body cũ còn ghi difflib >0.85.
**Bản implement đúng = rapidfuzz `token_set_ratio ≥ 90`** (`dedup.py`). → Cần sửa body decisions.md.

### 3.3 Fuzzy dedup gắn nhãn "Phase 4"
Lớp 2 có code + test + được gọi trong `run()` khi `fuzzy_dedup=True` (mặc định), nhưng comment
vẫn ghi "Phase 4" gây tưởng chưa bật. Thực tế đang chạy.

### 3.4 Legacy config còn sót
`config/domains.yaml` (số ít, cũ) chứa 3 domain (vnexpress, cafef, ndh) với CSS selectors +
api_url — KHÔNG phải nguồn active. 23 domain active nằm ở `config/domains/*.yaml`. Nên xoá để
tránh nhầm.

## 4. Bảo mật

- `config/secrets.yaml` (FireAnt token) **gitignored** — đã xác nhận `git check-ignore`. Không
  bao giờ commit/log giá trị token. Chỉ commit `secrets.yaml.example`.
- FireAnt token có thể hết hạn → 401 → scraper self-disable + ERROR log 1 lần. Cập nhật thủ công.

## 5. Ưu tiên xử lý (đề xuất)

| Ưu tiên | Việc |
|---|---|
| Cao | (1.1) Chốt 1 scheduler · (2.1) Backfill sentiment CafeF |
| Trung | (1.2) Retention DB · (3.1) Test hose · (3.2) Sửa decisions.md |
| Thấp | (1.3) Đo cycle-time · (3.4) Xoá legacy config |
