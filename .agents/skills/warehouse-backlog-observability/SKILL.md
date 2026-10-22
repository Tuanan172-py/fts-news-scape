---
name: warehouse-backlog-observability
description: Bức tranh toàn cảnh kho dữ liệu, bản đồ đa chiều bài viết tồn đọng và quy chế điều phối cuốn chiếu (Rolling Waves) dành cho Operator quản lý Conductor trong hệ thống News-Scape.
---

# Warehouse State & Backlog Observability Skill (Operator Guide)

> **Tầm nhìn & Mục tiêu:** Cung cấp cho **Operator quản lý các Conductor** bức tranh toàn cảnh về kho dữ liệu (31.704 bài), bản đồ phân bổ đa chiều của **22.676 bài tồn đọng chưa qua LLM** (theo Tiers ưu tiên, trục thời gian, nguồn báo, hàng đợi), quy chế phân định thẩm quyền Operator vs Conductor, chiến lược điều phối cuốn chiếu 4 pha và công cụ trinh sát 0-token `pipeline_radar.py backlog`.

---

## 1. Toàn Cảnh Kho Dữ Liệu & Các Tầng Thông Tin (Warehouse State & Layers)

Tính đến ngày **16/10/2026**, kho CSDL trung tâm (`monocle.db`) ghi nhận tổng cộng **31.704 bài viết** được thu thập:

| Tầng dữ liệu / Trạng thái | Số lượng (bài) | Tỷ lệ (%) | Ý nghĩa nghiệp vụ |
| :--- | :---: | :---: | :--- |
| **Tổng số bài thu thập (articles)** | **31.704** | **100,0%** | Tổng dung lượng kho bài đã cào và chuẩn hóa Silver. |
| **Đã phân tích Gold (DoD Pass)** | **9.028** | **28,5%** | Đã qua mô hình LLM phân tích sâu (summary, key_points, implications, sentiment, time_sensitivity, citations) đạt chuẩn Definition-of-Done. |
| **TỒN ĐỌNG CHƯA PHÂN TÍCH GOLD** | **22.676** | **71,5%** | **Khối lượng công việc cần Conductor giải phóng theo kế hoạch.** |
| • *Đã qua L1 bằng LLM đạt chuẩn* | 11.727 | 37,0% | Đã nhận diện thực thể ngữ nghĩa sâu bằng LLM. |
| • *L1 Code-First nạp nhanh* | 3.069 | 9,7% | Nhận diện thực thể máy móc qua từ điển cứng (chưa qua LLM). |
| • *Kế thừa cụm tin trùng (Cluster Copy)* | 292 | 0,9% | Tự động kế thừa kết quả từ bài đại diện (canonical) theo ADR 0016. |
| **Trạng thái hàng đợi `work_items`** | | | `pending`: 20.636 · `done`: 8.851 · `held`: 18 · `failed`: 1. |

---

## 2. Bản Đồ Đa Chiều Bài Viết Tồn Đọng (Multidimensional Backlog Map)

### 2.1. Phân Loại Theo Mức Độ Ưu Tiên (Priority Tiers)

Toàn bộ 22.676 bài tồn đọng được phân thành 2 nhóm ưu tiên độc lập:

1. **TIER 1 — Giao Hàng Ngay (Watchlist Người Dùng & Vĩ Mô Khẩn Cấp):**
   - **Số lượng:** **11.367 bài (50,1%)**
   - **Đặc điểm:** Chứa mã cổ phiếu trong danh mục chủ động của người dùng (`config/entities/users/*.yaml`, ví dụ: AnPT với SSI, VND, VIC, VHM, HPG, FPT...) hoặc chứa từ khóa biến động vĩ mô khẩn cấp (NHNN, lãi suất điều hành, tỷ giá, GDP, CPI, thuế tự vệ).
   - **Chính sách:** Đóng gói ưu tiên xử lý trước, kích hoạt xuất bản Excel deliverable giao cho người dùng ngay sau khi nạp xong đợt.
2. **TIER 2 & 3 — Hàng Đợi Nền (Thị Trường Chung & Lịch Sử):**
   - **Số lượng:** **11.309 bài (49,9%)**
   - **Đặc điểm:** Cổ phiếu ngoài watchlist, tin công bố hành chính định kỳ, bài tổng hợp thị trường chung.
   - **Chính sách:** Gom lô xử lý cuốn chiếu ở các đợt nền để làm giàu kho phân tích dữ liệu lịch sử với độ phủ 100%.

### 2.2. Phân Bổ Theo Trục Thời Gian (Timeline Distribution)

```
                            TỔNG TỒN ĐỌNG (22.676 bài)
                                        │
    ┌───────────────────────┬───────────┴───────────┬───────────────────────┐
    ▼                       ▼                       ▼                       ▼
[DỮ LIỆU NÓNG GẦN NHẤT] [TRUNG HẠN T09 & T08]   [LỊCH SỬ < 08/2026]     [KHUYẾT NGÀY ĐĂNG]
 (Tháng 10: 3.340 bài)   (T09+T08: 11.928 bài)     (1.971 bài)             (5.370 bài)
    │                       │                       │                       │
    ├─ 16/10:    38 bài     ├─ T09/2026: 7.451 bài  └─ Bài từ 2017 -> 2026: └─ Thu thập từ cào bù
    ├─ 15/10:   601 bài     └─ T08/2026: 4.477 bài     chưa có phân tích       sitemap, thiếu meta
    ├─ 14/10:   633 bài                                                        ngày (xử lý gom lô)
    ├─ 13/10:   608 bài
    ├─ 12/10:   338 bài
    ├─ 09/10:   513 bài
    └─ 01->08:  609 bài
```

### 2.3. Phân Bổ Theo Nguồn Thu Thập (Source Domains)

| STT | Nguồn tin (Domain) | Tổng bài | Đã xử lý Gold | Tồn đọng (Pending) | Tỷ lệ tồn | Ghi chú vận hành |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | `cafef.vn` | 14.890 | 3.347 | **11.543** | 77,5% | Nguồn lớn nhất, chiếm 50,9% tổng tồn đọng toàn hệ thống. |
| 2 | `tinnhanhchungkhoan.vn`| 3.047 | 544 | **2.503** | 82,1% | Tin chuyên sâu chứng khoán và doanh nghiệp niêm yết. |
| 3 | `vneconomy.vn` | 3.715 | 1.227 | **2.488** | 67,0% | Tin kinh tế vĩ mô, ngân hàng và tài chính quốc tế. |
| 4 | `vietstock.vn` | 3.428 | 1.077 | **2.351** | 68,6% | Tin giao dịch cổ đông, BCTC và thông tin doanh nghiệp. |
| 5 | `baodautu.vn` | 2.379 | 1.095 | **1.284** | 54,0% | Dự án đầu tư, FDI, bất động sản và chính sách. |
| 6 | `fireant.vn` | 1.404 | 428 | **976** | 69,5% | Tin vắn cộng đồng và thông cáo thị trường. |
| 7 | `vietnambiz.vn` | 1.697 | 769 | **928** | 54,7% | Phân tích ngành, vĩ mô và doanh nghiệp. |
| 8 | `thoibaotaichinhvietnam.vn` | 1.144 | 541 | **603** | 52,7% | Cơ chế chính sách thuế, hải quan và thị trường vốn. |

---

## 3. Quy Chế Quản Lý Operator vs Conductor (Governance & Roles)

### 3.1. Phân Định Thẩm Quyền (Taxonomy)

1. **Operator (Người Quản Trị Hệ Thống - Human / Supervisor):**
   - **Trách nhiệm:**
     - Thiết lập hạn mức ngân sách token và kiểm soát chi phí API.
     - Quyết định chiến lược phân kỳ xử lý tồn đọng (chọn ngày, chọn đợt, cấp hạn ngạch `--limit`).
     - Duyệt danh mục người dùng và phân tầng Tickers (`manifest.yaml`).
     - Giám sát sức khỏe kho dữ liệu qua `pipeline_radar.py backlog` và `status`.
   - **Công cụ độc quyền:** Chỉ định chính sách, cấp ngân sách đợt, kiểm toán sổ cái token (`token_ledger.py report`).
2. **Conductor (Tác Nhân Điều Phối Đợt - Automated Agent / Subagent):**
   - **Trách nhiệm:**
     - Thực thi quy trình khép kín cho đúng 1 mã đợt được giao (`wave_id`): Đóng gói $\rightarrow$ Gọi Worker nhận thức $\rightarrow$ Kiểm định DoD $\rightarrow$ Nạp SQLite $\rightarrow$ Xuất bản Deliverables.
     - Tự động kích hoạt vòng sửa chữa (`--repair`) nếu phát hiện bài thiếu hoặc hỏng schema.
     - Đảm bảo tính toàn vẹn của giao dịch DB: đợt chỉ xong khi `--finish` thoát 0 và in ✅.
   - **Quy tắc bất biến:** Tuân thủ WIP = 1 per Worktree; không được tự ý sửa đổi schema hay bypass cổng kiểm định DoD.

---

## 4. Kính Ngắm Trinh Sát Duy Nhất (Single Observability Lens)

Tuyệt đối không chạy script ad-hoc để thăm dò SQLite. Sử dụng các lệnh chính thức sau:

```powershell
# 1. Báo cáo toàn cảnh kho dữ liệu, phân tầng, thời gian, domain & lệnh khuyến nghị:
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/pipeline_radar.py backlog

# 2. Kiểm tra độ tươi và điểm chạm đợt của ngày hôm nay (hoặc ngày cụ thể):
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/pipeline_radar.py status [--date YYYY-MM-DD]

# 3. Kiểm toán chi phí và lượng token thực tế đã tiêu thụ theo đợt:
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/pipeline_radar.py token --wave <mã_đợt>

# 4. Giám sát danh sách người dùng và phát hiện file đăng ký mới:
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/pipeline_radar.py users
```

---

## 5. Chiến Lược Điều Phối Cuốn Chiếu 4 Pha (Rolling Waves Roadmap)

### Dự toán Chi phí & Thời gian:
- **Mô hình định tuyến:** runner `agy` (Gemini 3.8 Flash) là chính, rồi `opencode`, rồi `openrouter` (ADR-0026.D3); chi phí đọc từ sổ cái `token_ledger`.
- **Tổng ngân sách:** ~$5,22 USD cho toàn bộ 22.676 bài tồn đọng.
- **Thời gian xử lý:** ~8-10 phút / đợt 500 bài; tổng thời gian ~6-7 giờ chia thành ~46 waves.

### Lộ Trình Thực Thi:

#### Pha 1: Dữ Liệu Nóng Gần Nhất (Tháng 10/2026 — 3.340 bài)
Ưu tiên xử lý cuốn chiếu theo ngày từ mới nhất trở về trước để cấp nhật BCTC và tin tức mới nhất cho các chuyên viên phân tích:
- **Thứ tự thực hiện:** `2026-10-15` (601 bài) $\rightarrow$ `2026-10-14` (633 bài) $\rightarrow$ `2026-10-13` (608 bài) $\rightarrow$ `2026-10-09` (513 bài) $\rightarrow$ Các ngày lẻ còn lại.
- **Lệnh điều phối mẫu (Conductor Runbook):**
  ```powershell
  # Bước 1: Đóng gói và quét bài theo ngày
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_OCT15 --date 2026-10-15 --runner agy

  # Bước 2: Chạy phân tích nhận thức (Single-turn, Zero-tool)
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_OCT15 --runner agy --analyze --concurrency 1

  # Bước 3 (nếu có bài thiếu): Vòng vá tự động
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_OCT15 --repair --runner agy --concurrency 1

  # Bước 4: Nghiệm thu DoD và nạp kho CSDL SQLite
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_OCT15 --finish

  # Bước 5: Xuất bản và phân phối báo cáo Excel giao hàng
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/write_user_output.py --date 2026-10-15
  ```

#### Pha 2: Dữ Liệu Trung Hạn (Tháng 09 & 08/2026 — 11.928 bài)
Gom đợt 500 bài/lô theo cơ chế ưu tiên Tier 1 (Watchlist & Vĩ mô khẩn) trước, Tier 2/3 sau:
- **Lệnh điều phối mẫu:**
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_SEP_B01 --limit 500 --runner agy
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_SEP_B01 --runner agy --analyze --concurrency 1
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_SEP_B01 --finish
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/write_user_output.py          # bỏ --date = mọi ngày
  ```

#### Pha 3: Nhóm Khuyết Ngày Đăng (5.370 bài) & Lịch Sử Cũ (< 08/2026 — 1.971 bài)
Xử lý giải phóng dữ liệu cào bù sitemap và các sự kiện lịch sử để hoàn thiện kho tri thức dài hạn.

#### Pha 4: Hoàn Thiện Hàng Đợi Nền & Kiểm Toán Toàn Diện
Cụm hóa câu chuyện (`story_cluster.py`) và cập nhật bảng tín hiệu insight (`signal_build.py`).

---

## 6. Rào Cản Kỹ Thuật & Cạm Bẫy SQLite Cần Ghi Nhớ (Guardrails)

1. **Cạm bẫy chuỗi rỗng trong so sánh ngày SQLite:**
   - Trong SQLite, chuỗi rỗng `''` có thể thỏa mãn các phép so sánh ký tự nếu không kiểm tra cẩn thận.
   - **Bắt buộc:** Luôn có điều kiện bảo vệ `WHERE a.published_at IS NOT NULL AND a.published_at != '' AND ...`.
2. **Quy tắc Single-Turn Zero-Tool cho Subagent:**
   - Worker nhận thức KHÔNG được cấp công cụ truy cập đĩa hay công cụ tìm kiếm. Trả kết quả JSON trực tiếp trong final turn.
3. **Không dùng `--force` mặc định:**
   - Staging an toàn và kiểm SHA-256 luôn chạy, không cần cờ. `article_run.py --force` bỏ qua kiểm va chạm với đợt `ops_daemon` và khoá provider; `write_user_output.py --force` ghi đè mọi tệp giao hàng. Chỉ dùng khi có lý do cụ thể.
