# US-013 — Radar cảnh báo 404 giả + Guard rail Bronze cho domain đang bật

- **Status:** implemented
- **Lane:** normal
- **Parent / Epic:** Bronze Ingestion Pipeline
- **Intake date:** 2026-09-17 (intake #13)
- **Depends On:** US-011 (metric `source_deleted`)

## Product Contract

Không thể bật một domain không lưu Bronze mà không bị test chặn lại. Và một đợt tăng vọt 404 tập
trung ở một domain phải được radar gọi tên là **nghi vấn đổi cấu trúc URL**, thay vì để người đọc
tin nhầm rằng đó là tin bị gỡ thật.

## Acceptance Criteria

- [x] `pipeline_radar.py` truy vấn `source_deleted` theo `GROUP BY source_domain`.
- [x] Đẩy cảnh báo `HIGH` khi một domain có **>10 bài** 404/410 **và** chiếm **>30%** số bài của
      domain đó trong ngày, kèm lệnh `validate_capture.py <domain>`.
- [x] `test_enabled_domains_must_capture_bronze` — đỏ nếu có domain `enabled: true` mà scraper không
      kế thừa `CaptureMixin`.
- [x] `test_generic_rss_capture_domains_declare_content_selector` — đỏ nếu domain dùng
      `RssCaptureScraper` chung mà thiếu `detail.content_selector`.
- [x] Thông điệp assert trỏ thẳng tới `project/docs/dev/03-adding-a-source.md` §2b.
- [x] `validate_capture.py` in rõ danh sách domain đang bật bị bỏ qua vì không khai `capture:`.

## Design Notes

Chọn **guard rail thay vì migrate 15 domain**: mỗi domain cần xác minh selector trên trang thật theo
checklist `03-adding-a-source.md` §2b — việc thật, và chỉ cần khi thực sự bật lại. Guard rail chặn
đúng khoảnh khắc rủi ro (lúc ai đó đặt `enabled: true`) với chi phí gần bằng 0.

**Guard rail bắt được giới hạn của chính nó.** Phiên bản đầu áp cho **mọi** subclass `CaptureMixin`
đã báo động giả với `fireant`: đó là nguồn API, Bronze là JSON nên CSS `content_selector` vô nghĩa.
Kiểm tra thêm cho thấy các scraper chuyên dụng (cafef `div#mainContent`, vneconomy `#article-editor`,
tnck `div.article__body`, baodautu `#content_detail_news`, vietstock …) đều có default **đã verify cho
đúng site đó**. Chỉ `rss_capture.py:50` mới có default đoán mò `"article"`. Đã thu hẹp assert đúng về
`RssCaptureScraper`. Bài học: guard rail phải khớp vùng rủi ro thật, không áp theo kiểu phân loại lớp.

## Validation

| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/test_orchestrator.py -q` | passed | 7 passed; full suite 403 passed |
| Integration | — | — | radar cần DB thật, kiểm bằng chạy tay |
| E2E | — | — | |
| Platform | — | — | |

## Evidence — chứng minh RED/GREEN thật

Tạm đặt `enabled: true` cho `project/config/domains/znews.yaml` (`method: rss`):

```
FAILED tests/test_orchestrator.py::test_enabled_domains_must_capture_bronze
AssertionError: Domain đang bật nhưng KHÔNG lưu Bronze: znews (method=rss).
Xem checklist project/docs/dev/03-adding-a-source.md §2b trước khi bật ...
```

Hoàn tác → `git diff --stat project/config/domains/znews.yaml` rỗng, test xanh lại (7 passed).

## Harness Delta

none.

## Trace (inline)

- **Trace:** #47, `score_trace = 1.0`, `score_context = 1.0`.
- **Outcome:** completed.
