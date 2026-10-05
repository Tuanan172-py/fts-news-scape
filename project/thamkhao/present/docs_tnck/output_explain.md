## Cấu trúc bài đăng sau xử lý (Processed Article Schema)

Mỗi bài viết sau khi được `process_raw_response.py` xử lý từ log thô API TNCK
sẽ có **19 fields**, chia thành 6 nhóm chức năng.

---
### 1 bài viết hoàn chỉnh

```json
{
  "ticker": "TV2",
  "content_id": 384814,
  "title": "Dịch vụ Phân phối Tổng hợp Dầu khí (PSD) vượt 40% mục tiêu lợi nhuận 2025",
  "sub_title": "",
  "description": "(ĐTCK) Năm 2025, CTCP Dịch vụ Phân phối Tổng hợp Dầu khí (Petrosetco Distribution, mã PSD) ghi nhận 143,1 tỷ đồng lợi nhuận sau thuế, tăng 73% so với năm trước và vượt 40% mục tiêu năm.",
  "date_unix": 1770108462,
  "date_str": "2026-02-03 15:47:42",
  "update_time_unix": 1770108462,
  "update_time_str": "2026-02-03 15:47:42",
  "full_url": "https://www.tinnhanhchungkhoan.vn/dich-vu-phan-phoi-tong-hop-dau-khi-psd-vuot-40-muc-tieu-loi-nhuan-2025-post384814.html",
  "relative_url": "/dich-vu-phan-phoi-tong-hop-dau-khi-psd-vuot-40-muc-tieu-loi-nhuan-2025-post384814.html",
  "avatar_url": "https://image.tinnhanhchungkhoan.vn/w200/Uploaded/2026/xvrhgenatpx97/2026_02_03/492389603-...-n-8553-4165.jpg",
  "avatar_description": "",
  "source": "",
  "source_url": "",
  "zone_id": 4,
  "zone_name": "Thông tin doanh nghiệp",
  "zone_url": "/thong-tin-doanh-nghiep/",
  "related_tickers": "BMI,C4G,DL1,FPT,GCF,GMD,HUT,IDC,ITD,MBB,MWG,PAC,PC1,PVD,PVS,SHB,SIP,STH,TIP,TV2,VGT"
}
```

---
### Bảng chi tiết 19 fields
#### Nhóm 1 — Truy vết mã cổ phiếu

| #   | Field             | Type  | Nguồn              | Mô tả                                                                                                                                                         |
| --- | ----------------- | ----- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `ticker`          | `str` | Metadata bọc ngoài | Mã CP trong watchlist đã dùng để gọi API (`phrase`). **Không có trong JSON gốc của TNCK** — được gắn vào từ `responses[i].ticker`.                            |
| 2   | `related_tickers` | `str` | Tính toán mới      | Danh sách **tất cả ticker** mà bài viết này xuất hiện trong kết quả, phân cách bằng dấu phẩy, sắp theo ABC. Dùng để biết bài viết liên quan đến những mã nào. |

#### Nhóm 2 — Định danh bài viết

| # | Field | Type | Nguồn | Mô tả |
|---|-------|------|-------|-------|
| 3 | `content_id` | `int` | API gốc | ID nội bộ của bài viết trên hệ thống TNCK. Là **khoá chính** để nhận diện bài viết, dùng cho dedup. |

#### Nhóm 3 — Nội dung bài viết

| #   | Field         | Type  | Nguồn                  | Mô tả                                                                                                                                           |
| --- | ------------- | ----- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 4   | `title`       | `str` | API gốc                | Tiêu đề bài viết. Đã được `.strip()`.                                                                                                           |
| 5   | `sub_title`   | `str` | API gốc                | Phụ đề. Thường rỗng `""`.                                                                                                                       |
| 6   | `description` | `str` | API gốc → **đã xử lý** | Sapo/tóm tắt bài viết. Đã được: (1) `html.unescape()` để chuyển `&nbsp;`, `&amp;`... về ký tự thường, (2) normalize whitespace, (3) `.strip()`. |

#### Nhóm 4 — Thời gian

| # | Field | Type | Nguồn | Mô tả |
|---|-------|------|-------|-------|
| 7 | `date_unix` | `int` | API gốc | Unix timestamp (giây) — thời điểm **đăng bài**. Giữ nguyên từ API. |
| 8 | `date_str` | `str` | **Tính toán mới** | Chuyển đổi từ `date_unix` sang dạng đọc được: `YYYY-MM-DD HH:MM:SS` theo **múi giờ Việt Nam (UTC+7)**. |
| 9 | `update_time_unix` | `int` | API gốc | Unix timestamp (giây) — thời điểm **cập nhật gần nhất**. |
| 10 | `update_time_str` | `str` | **Tính toán mới** | Chuyển đổi từ `update_time_unix`, cùng format và múi giờ như `date_str`. |

#### Nhóm 5 — Đường dẫn & hình ảnh

| # | Field | Type | Nguồn | Mô tả |
|---|-------|------|-------|-------|
| 11 | `full_url` | `str` | **Tính toán mới** | URL đầy đủ tới bài viết, ghép host `https://www.tinnhanhchungkhoan.vn` + `relative_url`. Click được ngay. |
| 12 | `relative_url` | `str` | API gốc | Đường dẫn tương đối từ API, dạng `/ten-bai-viet-post{id}.html`. |
| 13 | `avatar_url` | `str` | API gốc | URL ảnh đại diện (thumbnail w200) của bài viết. |
| 14 | `avatar_description` | `str` | API gốc | Caption ảnh đại diện, thường rỗng. |

#### Nhóm 6 — Nguồn & chuyên mục

| # | Field | Type | Nguồn | Mô tả |
|---|-------|------|-------|-------|
| 15 | `source` | `str` | API gốc | Tên nguồn nếu bài được lấy lại từ nơi khác. Rỗng nếu bài gốc ĐTCK. |
| 16 | `source_url` | `str` | API gốc | URL nguồn gốc. Thường rỗng. |
| 17 | `zone_id` | `int` | API gốc → flatten | ID chuyên mục. `4` = *Thông tin doanh nghiệp*. Được flatten từ object `zone` gốc. |
| 18 | `zone_name` | `str` | API gốc → flatten | Tên chuyên mục hiển thị. Flatten từ `zone.name`. |
| 19 | `zone_url` | `str` | API gốc → flatten | Đường dẫn chuyên mục. Flatten từ `zone.url`. |

---

### So sánh
```
RAW (API gốc)                              PROCESSED (sau xử lý)
─────────────────────────────────────       ─────────────────────────────────────
❌ Không có field ticker                    ✅ ticker: "TV2"
❌ date: 1770108462 (không đọc được)        ✅ date_str: "2026-02-03 15:47:42"
❌ description chứa &nbsp;                  ✅ description đã unescape, sạch
❌ url: "/...post384814.html" (relative)    ✅ full_url: "https://www...html"
❌ zone: { zone_id, name, url } (nested)    ✅ zone_id, zone_name, zone_url (flat)
❌ 12 field layout (show_ads, show_...)      ✅ Đã loại bỏ — không cần cho phân tích
❌ Không biết bài liên quan ticker nào       ✅ related_tickers: "BMI,C4G,FPT,..."
```

---
### Các field bị LOẠI BỎ từ API gốc

Những field sau chỉ phục vụ giao diện frontend TNCK

| Field bị loại | Lý do |
|----------------|-------|
| `display_type` | Kiểu layout hiển thị (0, 11...) |
| `attributes` | Thuộc tính bài viết nội bộ |
| `content_type` | Loại nội dung |
| `content_icon` | Icon nội dung |
| `show_title` | Cờ ẩn/hiện tiêu đề |
| `show_sapo` | Cờ ẩn/hiện sapo |
| `show_avatar` | Cờ ẩn/hiện ảnh đại diện |
| `show_comment` | Cờ ẩn/hiện bình luận |
| `show_ads` | Cờ ẩn/hiện quảng cáo |
| `show_audio` | Cờ ẩn/hiện audio |
| `redirect_link` | Link redirect (luôn rỗng) |
| `frame_link` | Link frame (luôn rỗng) |

---