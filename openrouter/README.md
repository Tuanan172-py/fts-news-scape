# OpenRouter & 9Router Gateway Integration

Thư mục chứa toàn bộ cấu hình, script kiểm tra và chốt kiểm định dữ liệu phục vụ tích hợp OpenRouter (đặc biệt là các model Stealth như `stealth/space-bunny-alpha`) và Google Gemini AI Studio thông qua trạm điều phối trung gian **9Router**.

---

## 1. Cấu Trúc Thư Mục

```text
openrouter/
├── docker-compose.yml     # Khởi chạy 9Router container trên cổng 20128
├── .env.example           # Mẫu cấu hình khóa API (OpenRouter, Gemini, Router)
├── .gitignore             # Bảo vệ không commit khóa API bí mật
├── schemas.py             # Data Contract Pydantic & bộ lọc trích xuất JSON
├── client.py              # Wrapper OpenAI-compatible gọi qua Gateway hoặc trực tiếp
├── test_connection.py     # Script kiểm tra kết nối, đo latency & nghiệm thu schema
└── README.md              # Tài liệu hướng dẫn chi tiết
```

---

## 2. Quy Trình Thiết Lập & Vận Hành

### Bước 1: Khởi động 9Router Container

Mở PowerShell tại thư mục này và khởi động Docker container:

```powershell
# Chuyển vào thư mục openrouter và khởi động bằng docker compose
docker compose -f openrouter/docker-compose.yml up -d
```

Hoặc chạy lệnh Docker trực tiếp:

```powershell
docker run -d `
  --name 9router `
  -p 20128:20128 `
  -v "$HOME/.9router:/app/data" `
  -e DATA_DIR=/app/data `
  --restart unless-stopped `
  decolua/9router:latest
```

*Kiểm tra trạng thái:* Mở trình duyệt truy cập Web UI tại `http://localhost:20128`.

---

### Bước 2: Cấu hình Khóa API trên 9Router Web UI

1. **OpenRouter:**
   * Vào **Providers** $\rightarrow$ **Add Provider** $\rightarrow$ Chọn **OpenRouter**.
   * Dán `OPENROUTER_API_KEY` (khóa tài khoản đã nạp tối thiểu $10 để giữ hạn mức 1.000 requests/ngày cho các model miễn phí/stealth).
2. **Google Gemini:**
   * Chọn **Add Provider** $\rightarrow$ Chọn **Google Gemini / AI Studio**.
   * Dán `GEMINI_API_KEY` (lấy miễn phí từ [aistudio.google.com](https://aistudio.google.com)).
3. **Kiểm tra kết nối:**
   * Nhấn nút kiểm tra kết nối (Test connection) cho cả hai provider trên Web UI.

---

### Bước 3: Cấu hình Cursor IDE Trỏ Về Local Gateway

1. Mở **Cursor Settings** (`Ctrl + Shift + J`).
2. Chọn tab **Models**:
   * **OpenAI API Key:** Nhập `sk-9router-local` (chuỗi ký tự bất kỳ).
   * Bật **Override OpenAI Base URL**.
   * Nhập Base URL: `http://localhost:20128/v1`
3. Thêm Model mới:
   * Nhấn **+ Add Model**.
   * Nhập chính xác tên: `stealth/space-bunny-alpha` $\rightarrow$ Nhấn **Save**.
   * Tắt các model mặc định khác để Cursor ưu tiên dùng model này.
4. Thử nghiệm trên Composer (`Ctrl + I`): Đính kèm file lớn hoặc prompt lập trình để kiểm chứng tốc độ xử lý ngữ cảnh và chi phí $0 trên OpenRouter.

---

### Bước 4: Kiểm Thử Kết Nối Bằng Script Python

Chạy script kiểm tra để gửi một truy vấn phân tích tài chính mẫu, đo đạc thời gian phản hồi và kiểm định schema:

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" openrouter/test_connection.py
```

Tùy chọn kiểm tra với model khác:

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" openrouter/test_connection.py --model google/gemini-2.0-flash-exp:free
```

---

### Bước 5: Tích Hợp Vào Đường Tự Động Hóa (Bảo Vệ Hệ Thống)

Khi nhân rộng quy mô xử lý hàng loạt tin tức / tài liệu, luôn gọi qua hàm có kiểm định schema trong `openrouter/client.py`:

```python
from openrouter.client import request_structured_completion

# Gọi suy luận an toàn - tự động lọc markdown rác và kiểm định Pydantic
result = request_structured_completion(
    prompt="Nội dung bài viết cần bóc tách dữ liệu...",
    model="stealth/space-bunny-alpha",
)

if result is not None:
    # Vượt qua kiểm định schema, an toàn để nạp Database hoặc ghi file
    print(result.summary)
    print(result.sentiment)
    print(result.materiality_score)
else:
    # Thất bại (sai cấu trúc, vi phạm enum hoặc timeout) -> Kích hoạt fallback
    print("Yêu cầu không hợp lệ, kích hoạt fallback sang Gemini...")
```
