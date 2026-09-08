# Domain Mastery — FireAnt (fireant.vn)

Nền tảng dữ liệu/cộng đồng chứng khoán. Tin **đã gắn sẵn mã CK** (`taggedSymbols`) —
điểm mạnh riêng so với mọi nguồn khác (các nguồn kia phải `tag_tickers` phía client).

---

## 1. Tổng quan

| Thuộc tính | Giá trị |
|-----------|--------|
| **Domain** | fireant.vn |
| **Phương thức** | REST API (Bearer token) + **Bronze capture JSON** |
| **Scraper** | `FireAntScraper` (`src/scrapers/fireant.py`), registry key `fireant` |
| **Auth** | `config/secrets.yaml` → `fireant_token` (JWT, exp 2036) |
| **Volume** | 30 mã × 20 = **600 item/cycle** (phần lớn trùng → dedup) |
| **Bronze** | `data/raw_html/fireant.vn/<yyyymmdd>/<hash>.html` — **nội dung là JSON** |
| **Trạng thái** | enabled 2026-09-07 |

## 2. ⚠️ Bronze là JSON, không phải HTML

Trang `fireant.vn/dashboard/content/{id}` là **Next.js SPA** — body bài không có trong
HTTP GET. Nguồn sự thật duy nhất là **response API detail**, trong đó `content` là HTML.

```
GET https://restv2.fireant.vn/posts/{post_id}
Authorization: Bearer <token>
→ {"postID":…, "title":…, "content":"<p>…</p>", "date":"…+07:00", …}
   ▲ Bronze byte-exact chính là body JSON này
```

- **KHÔNG** dùng `CaptureMixin._capture_and_extract`: hàm đó chạy CSS selector
  (`_looks_complete`) nên sẽ gắn `partial` **oan** cho mọi bài. Gọi thẳng `RawStore.save()`.
- `SilverBuilder` thấy `Content-Type: application/json` → bóc trường HTML qua
  `_html_from_json()` rồi mới trích. Không có bước này, `cleaned_text` sẽ nuốt cả
  key JSON và dấu ngoặc.
- Đuôi file Bronze vẫn là `.html` (quy ước layout của `RawStore`); **nội dung là JSON** —
  đọc `response_headers.content-type` trong `.meta.json` để biết.

## 3. Bẫy đã sửa 2026-09-07

| # | Bẫy | Sửa |
|---|---|---|
| 1 | API trả **camelCase** (`postID`, `postSource`, `postSourceUrl`) nhưng code đọc `post_source` snake_case → `source_name` **luôn rỗng** | đọc camelCase, fallback snake. Có test regression |
| 2 | `WEB_URL` = `/bai-viet/{id}` → **404** | đúng là `/dashboard/content/{id}` |
| 3 | `/post/{id}` số ít → 404 | dùng `/posts/{id}` **số nhiều** (đã sửa từ 2026-07-26) |
| 4 | List trả `content` rỗng | bắt buộc gọi detail |

## 4. Auth

- Token đọc từ `config/secrets.yaml` → `fireant_token`. Chấp nhận cả dạng dán kèm
  `"Bearer eyJ..."` (tự strip, không nhân đôi).
- Thiếu token / còn `PASTE_...` → scraper **tự disable**, không gọi API.
- 401/403 → **self-disable ngay trong cycle** (không hammer API) + ERROR log.
  **Không ghi Bronze** cho response lỗi auth — nó không phải nội dung bài.
- Cập nhật token: sửa tay `config/secrets.yaml` (xem `docs/skills/fireant.md`).

## 5. ⚠️ TUÂN THỦ — cần owner xác nhận

`robots.txt` của **fireant.vn** (2026-09-07):

```
User-agent: *
Content-Signal: search=yes, ai-train=no, use=reference
Allow: /

User-agent: ClaudeBot         Disallow: /
User-agent: GPTBot            Disallow: /
User-agent: CCBot             Disallow: /
User-agent: Google-Extended   Disallow: /
User-agent: Amazonbot / Applebot-Extended / Bytespider / meta-externalagent  Disallow: /
```

**Đọc thế nào:**
- Site **chặn tường minh** crawler AI và khai **`ai-train=no`**.
- Nhưng ta **không crawl website ẩn danh**: ta gọi `restv2.fireant.vn`
  (**không có robots.txt** — 404) bằng **token của chính người dùng** → quan hệ ở đây là
  **ToS/thoả thuận tài khoản**, không phải robots dành cho crawler.

**Luật cứng của dự án:** TUYỆT ĐỐI không dùng dữ liệu fireant để **huấn luyện/fine-tune**
model. Dùng cho phân tích nội bộ (`use=reference`) là phù hợp với tín hiệu site khai.

**Việc của owner:** rà ToS tài khoản FireAnt xem có cho phép truy xuất tự động không.
Nếu không → đặt lại `enabled: false`. Watch point `fa-w5` theo dõi robots đổi.

## 6. Bảo trì

- `python scripts/verify_quality.py fireant.vn` · `python scripts/domain_check.py --report fireant`
- 600 item/cycle nghe nhiều nhưng phần lớn bị dedup chặn; chi phí thật ở
  `max_details_per_cycle: 30`.
- `symbols` lấy từ `taggedSymbols` của API (đã gắn sẵn) → health threshold cao (0.8),
  khác các nguồn phải tag client-side.
