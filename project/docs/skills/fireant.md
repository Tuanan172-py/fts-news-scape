# Domain Skill: FireAnt (fireant.vn)

Verified live: 2026-07-24 (endpoint alive; 401 khi thiếu token).

| Thành phần | Chi tiết |
|-----------|---------|
| **Domain** | fireant.vn (restv2.fireant.vn) |
| **Method** | REST API, **Bearer token bắt buộc** |
| **Auth** | `Authorization: Bearer <token>` — token trong `config/secrets.yaml` key `fireant_token` |
| **List** | `GET https://restv2.fireant.vn/posts?symbol={S}&type=1&offset=0&limit=20` — per watchlist symbol |
| **Detail** | `GET https://restv2.fireant.vn/post/{post_id}` — field `content` = full HTML |
| **Fields (list)** | `post_id`, `title`, `description`, `content` (RỖNG ở list — cần detail), `date` (ISO sẵn `+07:00`), `taggedSymbols[].symbol`, `post_source.name/url` |
| **Canonical URL** | Không có trong response → dùng `https://fireant.vn/bai-viet/{post_id}` |
| **Token expired** | 401/403 → scraper **self-disable ngay** (không hammer), ERROR log 1 lần. Cập nhật token thủ công (quyết định Phase 1) |

## Lấy token (thủ công)

1. Mở https://fireant.vn, đăng nhập
2. F12 → Network → filter `restv2.fireant.vn` → chọn request bất kỳ
3. Copy header `Authorization: Bearer eyJ...` (bỏ chữ "Bearer ")
4. Dán vào `config/secrets.yaml`: `fireant_token: "eyJ..."`

## Behavior notes

- Thiếu token/placeholder → scraper disabled từ constructor (WARN, không crash).
- 401 giữa cycle → các symbol còn lại bị skip; article đã parse giữ description làm content.
- Detail cap 30/cycle. `date` dùng nguyên bản (đã ISO VN tz).
