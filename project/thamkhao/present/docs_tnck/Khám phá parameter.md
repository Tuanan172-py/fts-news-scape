# TNCK API Explorer

Thư mục khám phá **tất cả zones, parameters, và endpoints** của TinNhanhChungKhoan API.
Dữ liệu lưu **nguyên bản RAW JSON** từ API, chưa qua xử lý/format.

---

## Kết quả khám phá

### 1. Danh sách tất cả zones (43 zone có dữ liệu)

| Zone | Tên | Parent | URL Slug |
|------|-----|--------|----------|
| 1 | **Chứng khoán** | 0 (root) | `/chung-khoan/` |
| 2 | **Cung - Cầu** | 0 (root) | `/cung-cau/` |
| 3 | **Thương trường** | 0 (root) | `/thuong-truong/` |
| 4 | **Thông tin doanh nghiệp** | 0 (root) | `/thong-tin-doanh-nghiep/` |
| 5 | **Bảo hiểm** | 60 | `/bao-hiem/` |
| 6 | **Tiền tệ** | 0 (root) | `/tien-te/` |
| 7 | **Vĩ mô** | 0 (root) | `/vi-mo/` |
| 8 | **Pháp đình** | — | `/phap-dinh/` |
| 9 | **Quốc tế** | 0 (root) | `/quoc-te/` |
| 10 | *(trống)* | — | — |
| 11 | **Trái phiếu** | 1 (CK) | `/trai-phieu/` |
| 12 | **Quốc tế (CK)** | 1 (CK) | `/ck-quoc-te/` |
| 13 | **Nhận định** | 1 (CK) | `/nhan-dinh/` |
| 14 | *(không có zone field)* | — | — |
| 15 | *(trống)* | — | — |
| 16 | **Đầu tư** | 63 | `/don-doc-bao-dau-tu/` |
| 17 | **Lịch sự kiện** | 0 (root) | `/lich-su-kien/` |
| 18-20 | *(trống)* | — | — |
| 21 | **Pháp luật (BĐS)** | 2 | `/bds-phap-luat/` |
| 22 | **Cung - Cầu** | 2 | `/cung-cau/` |
| 23 | **Phong thủy** | 2 | `/phong-thuy/` |
| 24 | **Chứng khoán** | 1 | `/chung-khoan/` |
| 25 | **Tiêu dùng** | 56 | `/tieu-dung/` |
| 26 | **Chuyên đề, sự kiện** | 0 (root) | `/chuyen-de-su-kien/` |
| 27 | **Doanh nghiệp tự giới thiệu** | 0 (root) | `/doanh-nghiep-tu-gioi-thieu/` |
| 28 | **Thông báo - bố cáo** | 0 (root) | `/thong-bao-bo-cao/` |
| 29 | **Đại hội cổ đông** | 0 (root) | `/dai-hoi-co-dong/` |
| 30 | *(trống)* | — | — |
| 31 | **Cộng Đồng** | 5 | `/cong-dong/` |
| 32 | **Sản Phẩm** | 6 | `/san-pham/` |
| 33 | **Pháp đình** | 8 | `/phap-dinh/` |
| 34 | **Chứng khoán** | 1 | `/chung-khoan/` |
| 35 | **Chính trị** | 7 | `/chinh-tri/` |
| 36 | **Đầu tư** | 7 | `/dau-tu/` |
| 37 | **Xã hội** | 56 | `/xa-hoi/` |
| 38 | **Mua bán - Sáp nhập** | 3 | `/mua-ban-sap-nhap/` |
| 39 | **Bảo hiểm xã hội** | 60 | `/bao-hiem-xa-hoi/` |
| 40 | **Doanh nghiệp tự giới thiệu** | 27 | `/doanh-nghiep-tu-gioi-thieu/` |
| 41 | **Thông tin doanh nghiệp** | 4 | `/thong-tin-doanh-nghiep/` |
| 42 | **Quy hoạch** | 2 | `/quy-hoach/` |
| 43 | **Vật liệu** | 2 | `/vat-lieu/` |
| 44 | **Trải nghiệm sống** | 2 | `/trai-nghiem-song/` |
| 45 | **Bên lề** | 1 (CK) | `/ben-le/` |
| 46 | **Phái sinh** | 1 (CK) | `/phai-sinh/` |
| 47 | **Chuyện kinh doanh** | 3 | `/chuyen-kinh-doanh/` |
| 48 | **Nhân sự** | 7 | `/nhan-su/` |

**Zones trống**: 10, 15, 18, 19, 20, 30, 49, 50

### 2. Zone hierarchy (parent → child)

```
Root (parent_id=0)
├── 1  Chứng khoán
│   ├── 11 Trái phiếu
│   ├── 12 Quốc tế (CK)
│   ├── 13 Nhận định
│   ├── 24 Chứng khoán
│   ├── 34 Chứng khoán
│   ├── 45 Bên lề
│   └── 46 Phái sinh
├── 2  Cung - Cầu (BĐS)
│   ├── 21 Pháp luật
│   ├── 22 Cung - Cầu
│   ├── 23 Phong thủy
│   ├── 42 Quy hoạch
│   ├── 43 Vật liệu
│   └── 44 Trải nghiệm sống
├── 3  Thương trường
│   ├── 38 Mua bán - Sáp nhập
│   └── 47 Chuyện kinh doanh
├── 4  Thông tin doanh nghiệp
│   └── 41 Thông tin doanh nghiệp
├── 5  Bảo hiểm
│   └── 31 Cộng đồng
├── 6  Tiền tệ
│   └── 32 Sản phẩm
├── 7  Vĩ mô
│   ├── 35 Chính trị
│   ├── 36 Đầu tư
│   └── 48 Nhân sự
├── 8  Pháp đình
│   └── 33 Pháp đình
├── 9  Quốc tế
├── 17 Lịch sự kiện
├── 26 Chuyên đề, sự kiện
├── 27 Doanh nghiệp tự giới thiệu
│   └── 40 DN tự giới thiệu
├── 28 Thông báo - bố cáo
└── 29 Đại hội cổ đông
```

### 3. API Endpoint

**Base URL**: `https://api.tinnhanhchungkhoan.vn/api`

**Endpoint duy nhất hoạt động**: `GET /morenews-zone-{zone}-{page}.html`

Các endpoint khác (lastnews, topnews, hotnews, search, categories, content, detail) đều trả về lỗi.

### 4. Query Parameters

| Parameter | Hoạt động | Giá trị | Mô tả |
|-----------|-----------|---------|-------|
| `phrase` | **CÓ** | string | Lọc theo keyword/ticker. VD: `phrase=VNM` |
| `page_size` | **CÓ** | 1-50 | Số articles/trang. **Max 50**. Default 40 |
| `limit` | **CÓ** | 1-50 | Giới hạn articles trả về. **Max 50**. Default 40 |
| `sort` | Không rõ | — | Không thấy thay đổi kết quả |
| `order` | Không rõ | — | Không thấy thay đổi kết quả |
| `from_date` | **KHÔNG** | — | API bỏ qua, trả kết quả giống nhau |
| `to_date` | **KHÔNG** | — | API bỏ qua, trả kết quả giống nhau |
| `category` | Không rõ | — | Không thấy thay đổi kết quả |
| `type` | Không rõ | — | Không thấy thay đổi kết quả |

**Lưu ý quan trọng**:
- `page_size` ưu tiên hơn `limit` khi dùng cùng lúc
- **Max trả về là 50 articles/request** dù set `page_size` hoặc `limit` > 50
- Pagination (page 1-20+) hoạt động ổn, mỗi page trả 40 articles theo thứ tự thời gian giảm dần

### 5. Response Structure (raw)

```json
{
  "data": {
    "contents": [...]       // Array of articles (24 fields mỗi article)
  },
  "error_code": 0,          // 0 = thành công
  "error_message": "",       // Rỗng nếu OK
  "server_time": 1739268812  // Unix timestamp
}
```

### 6. Article Fields (24 fields)

| # | Field | Type | Fill Rate | Mô tả |
|---|-------|------|-----------|-------|
| 1 | `content_id` | int | 100% | ID duy nhất của bài viết |
| 2 | `title` | string | 100% | Tiêu đề bài viết |
| 3 | `sub_title` | string | 0% | Tiêu đề phụ (luôn rỗng) |
| 4 | `description` | string | 100% | Sapo/mô tả ngắn (HTML) |
| 5 | `date` | int | 100% | Unix timestamp ngày đăng |
| 6 | `update_time` | int | 100% | Unix timestamp cập nhật |
| 7 | `avatar_url` | string | 100% | URL ảnh đại diện |
| 8 | `avatar_description` | string | 20% | Alt text của ảnh |
| 9 | `url` | string | 100% | URL bài viết (relative path) |
| 10 | `redirect_link` | string | 0% | Link redirect (luôn rỗng) |
| 11 | `frame_link` | string | 0% | Link iframe (luôn rỗng) |
| 12 | `display_type` | int | 100% | Kiểu hiển thị (thường = 0) |
| 13 | `attributes` | int | 100% | Attributes flags |
| 14 | `content_type` | string | 0% | Loại content (luôn rỗng) |
| 15 | `content_icon` | string | 0% | Icon (luôn rỗng) |
| 16 | `source` | string | 0% | Nguồn (luôn rỗng) |
| 17 | `source_url` | string | 0% | URL nguồn (luôn rỗng) |
| 18 | `show_title` | bool | 100% | Flag hiển thị title |
| 19 | `show_sapo` | bool | 100% | Flag hiển thị sapo |
| 20 | `show_avatar` | bool | 100% | Flag hiển thị avatar |
| 21 | `show_comment` | bool | 100% | Flag cho phép comment |
| 22 | `show_ads` | bool | 100% | Flag hiển thị quảng cáo |
| 23 | `show_audio` | bool | 100% | Flag hỗ trợ audio |
| 24 | `zone` | dict | 100%* | Object zone chứa: `zone_id`, `parent_id`, `name`, `url` |

(*) Zone 14 không có field `zone` trong response.

### 7. Zone field structure (nested dict)

```json
{
  "zone_id": 4,
  "parent_id": 0,
  "name": "Thông tin doanh nghiệp",
  "url": "/thong-tin-doanh-nghiep/"
}
```

### 8. Pagination behavior

- **Page 1** trả article mới nhất → Page N trả article cũ hơn
- Mỗi page = 40 articles (default), có thể thay bằng `page_size`
- Deep pagination: Test 20 pages x 40 articles = **800 articles** cho zone 4 + phrase=VNM, span từ Oct 2025 → Feb 2026
- Không có content trùng lặp giữa các zone khác nhau (0 duplicates trên 600 articles test)

### 9. Sample article (Zone 4, raw)

```json
{
  "content_id": 384804,
  "title": "Doanh thu Sao Ta (FMC) giảm 21% ngay tháng đầu năm 2026",
  "sub_title": "",
  "description": "(ĐTCK) CTCP Thực phẩm Sao Ta (FMC) công bố tình hình...",
  "date": 1770102267,
  "update_time": 1770102267,
  "avatar_url": "https://image.tinnhanhchungkhoan.vn/w200/Uploaded/2026/xvrhgenatpx97/2023_01_16/fmc-9473.jpg",
  "avatar_description": "",
  "url": "/doanh-thu-sao-ta-fmc-giam-21-ngay-thang-dau-nam-2026-post384804.html",
  "redirect_link": "",
  "frame_link": "",
  "display_type": 0,
  "attributes": 0,
  "content_type": "",
  "content_icon": "",
  "source": "",
  "source_url": "",
  "show_title": true,
  "show_sapo": true,
  "show_avatar": true,
  "show_comment": true,
  "show_ads": true,
  "show_audio": true,
  "zone": {
    "zone_id": 4,
    "parent_id": 0,
    "name": "Thông tin doanh nghiệp",
    "url": "/thong-tin-doanh-nghiep/"
  }
}
```


---

## Zones quan trọng cho trading/watchlist

| Ưu tiên | Zone | Tên | Lý do |
|---------|------|-----|-------|
| 1 | **4** | Thông tin doanh nghiệp | Tin DN, BCTC, sự kiện |
| 2 | **29** | Đại hội cổ đông | ĐHCĐ, nghị quyết |
| 3 | **13** | Nhận định | Phân tích, dự báo |
| 4 | **1/24/34** | Chứng khoán | Tin CK chung |
| 5 | **17** | Lịch sự kiện | Events calendar |
| 6 | **11** | Trái phiếu | Thị trường TP |
| 7 | **46** | Phái sinh | Thị trường PS |
| 8 | **38** | Mua bán - Sáp nhập | M&A |
| 9 | **48** | Nhân sự | Thay đổi nhân sự |
| 10 | **28** | Thông báo - bố cáo | Thông báo chính thức |
