# 14. Multi-tier Dynamic Entity System & User Mapping Architecture

## 1. Tổng quan & Mục tiêu (Overview)
Hệ thống Entity là trái tim định tuyến của nền tảng `news-scape`. Nó cho phép:
1. Nhận diện các đối tượng tài chính đa tầng (Mã cổ phiếu, Ngành nghề GICS 3 cấp, Địa chính trị/Quốc gia, Chủ đề vĩ mô, Loại tài sản, Định chế tài chính).
2. Tự động liên kết đa tầng (ví dụ: phát hiện mã HPG $\rightarrow$ tự động gắn ngành Thép).
3. Cho phép người dùng đăng ký linh hoạt (chỉ cần chọn mã tại các sheet trong master catalog) mà không cần cấu hình phức tạp.
4. Triệt tiêu false positive và bảo vệ các thuật ngữ ngắn có ý nghĩa kinh tế quan trọng.

---

## 2. Cấu trúc Ontology 10 Miền (Taxonomy)

| Nhóm Thực thể | Prefix Type | Cột tra cứu trong Excel | Ví dụ Mã (`code`) |
| :--- | :--- | :--- | :--- |
| **Cổ phiếu niêm yết** | `TICKER` | `Securities` | `HPG`, `FPT`, `VIC`, `SSI` |
| **Quỹ ETF / Mở** | `ETF` | `Securities` | `E1VFVN30`, `FUEVFVND` |
| **Khác (Quỹ đóng/TP)** | `SECURITY_OTHER` | `Securities` | `FUCTVGF3` |
| **Ngành GICS 3 cấp** | `INDUSTRY_GICS1/2/3` | `Industries` | `QUY`, `THEP`, `NGAN_HANG`, `BAT_DONG_SAN` |
| **Chỉ số thị trường** | `INDEX` | `Indices` | `VNINDEX`, `VN30`, `HNXINDEX` |
| **Sàn giao dịch** | `EXCHANGE` | `Exchanges` | `HOSE`, `HNX`, `UPCOM` |
| **Quốc gia & Địa chính trị** | `MACRO_GEO` | `Nations` | `MY`, `TRUNG_QUOC`, `EU`, `NHAT_BAN`, `NGA` |
| **Chủ đề Vĩ mô** | `MACRO_THEME` | `Themes` | `LAI_SUAT`, `TY_GIA`, `LAM_PHAT`, `DAU_TU_CONG` |
| **Loại tài sản** | `ASSET_CLASS` | `Assets` | `TRAI_PHIEU`, `CO_PHIEU`, `VANG`, `DAU_THO`, `TIEN_MA_HOA` |
| **Định chế & Quản lý** | `INSTITUTION` | `Institutions` | `NHNN`, `UBCKNN`, `BO_TAI_CHINH`, `FED`, `ECB` |

---

## 3. Quản lý Từ điển Alias Đa Miền (`config/entities/aliases/`)
Alias được tách nhỏ theo miền dữ liệu để bảo trì độc lập:
- `tickers.yaml`: Alias thương hiệu doanh nghiệp (FPT, Hòa Phát, Vingroup...).
- `industries.yaml`: Alias ngành nghề (Quỹ đầu tư, Venture capital, Luyện kim, Ngân hàng...).
- `nations.yaml`: Alias quốc gia, khu vực (Hoa Kỳ, Nhà Trắng, Bắc Kinh, Eurozone...).
- `themes.yaml`: Alias vĩ mô (Lãi suất điều hành, CPI, Tỷ giá USD/VND, Đầu tư công...).
- `assets.yaml`: Alias tài sản (TPDN, Vàng miếng SJC, Dầu Brent, Crypto...).
- `institutions.yaml`: Alias cơ quan (SBV, Cục Dự trữ Liên bang, World Bank...).

---

## 4. Cơ Chế Nhận Diện & Matcher Động (`src/agent/entities.py`)

### 4.1. Whitelist Từ Ngắn Được Bảo Vệ (`PROTECTED_SHORT_WORDS`)
Thay vì loại bỏ toàn bộ các từ ngắn `<4` ký tự gây mất các từ khóa vĩ mô cốt lõi, matcher sử dụng danh sách bảo vệ:
```python
PROTECTED_SHORT_WORDS = frozenset({
    "quy", "my", "us", "eu", "fed", "vang", "dau", "cpi", "gdp",
    "fomc", "sbv", "ecb", "boj", "omo", "noxh", "hrc", "ctck", "tctd", "bds",
})
```

### 4.2. Khớp Boundary Chống False Positive
Mọi alias khi tìm kiếm trên văn bản bỏ dấu đều sử dụng regex biên từ `\b...\b`:
```python
re.search(rf"\b{re.escape(alias_folded)}\b", folded_text)
```
Điều này đảm bảo các từ phức như *"quyết định"*, *"mỹ thuật"* không bao giờ bị nhận diện nhầm thành *"quy"* hay *"mỹ"*.

### 4.3. Đa ID per Alias
Một alias có thể ánh xạ tới nhiều ID (ví dụ cùng từ khóa *"Quỹ"* map sang cả `IND_GICS2:QUY` và `IND_GICS3:QUY`). Hệ thống lưu index dạng `dict[str, list[str]]` để không bị đè mất cấp độ.

---

## 5. Quy Trình Người Dùng & Phân Phối Tin (User Workflow & Output Gate)

```
[Master Excel: data/entities/entities.xlsx]
          │ (Tra cứu mã)
          ▼
[User Input Excel: users/input/<Name>/entities.xlsx]
          │ (Chạy compile.py)
          ▼
[User Config: config/entities/users/<Name>.yaml] (Active IDs)
          │
          │ ◄─── [Tin tức Silver + L1 Matched Entities]
          ▼
[Noise Filter Gate: user_output.py]
  - Macro/Asset diện rộng: Cần title mention HOẶC materiality_score >= 3
          │
          ▼
[User Excel Output: users/output/<Name>/news_YYYYMMDD.xlsx]
```
