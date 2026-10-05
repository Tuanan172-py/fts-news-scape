# Nghiên Cứu Đánh Đổi Kiến Trúc: Tích Hợp News-Scape Vào FPA Toolkit Monorepo

- **Ngày lập:** 2026-10-01
- **Chủ trì nghiên cứu:** Phạm Thành An (`anpt` / `FTA1`)
- **Đơn vị thẩm định:** Nguyễn Ngọc Đức (`ducnn2` / Head of Research)
- **Tài liệu căn cứ:** [`EPIC-03-ai-news-scanner.md`](file:///C:/Users/anpt/Documents/fpa-toolkit/docs/GE_rollout/epics/EPIC-03-ai-news-scanner.md), [`monorepo_master_roadmap.md`](file:///C:/Users/anpt/Documents/fpa-toolkit/docs/governance/monorepo_master_roadmap.md), [`GLB-DEC-068`](file:///C:/Users/anpt/Documents/fpa-toolkit/docs/adr/GLB-DEC-068-satellite-package-quarantine-and-agent-driven-bidirectional-parity-architecture.md)
- **Kỹ năng áp dụng:** [`evaluating-trade-offs`](file:///c:/Users/anpt/OneDrive%20-%20fpts.com.vn/FRA_DataIngestion%20-%20news-scape/.agents/skills/evaluating-trade-offs/SKILL.md)

---

## 1. Khung SCQA: Bối Cảnh, Xung Đột & Câu Hỏi Quyết Định

### 1.1. Situation (Bối cảnh thực tế)
- Dự án `news-scape` (`c:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape`) là một hệ thống thu thập và phân tích tin tức tài chính hoàn chỉnh, vận hành tự động theo chu kỳ nhiều đợt trong ngày (Scraper, Bronze raw HTML, Silver dedup SimHash, Gold Cognitive Worker LLM, CSDL SQLite `monocle.db`, bộ xuất bản Excel cá nhân hóa và catalog OKF).
- Monorepo [`fpa-toolkit`](https://github.com/Research-FPA/fpa-toolkit) (`C:\Users\anpt\Documents\fpa-toolkit` / `~/fpa-toolkit`) là nền tảng nghiên cứu tài chính và định lượng tập trung của Khối Phân tích (FPTS), bao gồm các phân hệ FFA (Phân tích cơ bản), FQS (Định lượng), FTA (Kỹ thuật), Admin và Shared Platform.
- Monorepo đã đăng ký chính thức nhiệm vụ tích hợp của AnPT tại **[Epic 3: AI News Scanner & Big Data Ingestion](file:///C:/Users/anpt/Documents/fpa-toolkit/docs/GE_rollout/epics/EPIC-03-ai-news-scanner.md)**, với phạm vi dự kiến gồm `shared/news/`, `shared/okf_base/news/` và `tests/shared/unit/test_news*.py`.

### 1.2. Complication (Xung đột & Điểm nghẽn kiến trúc)
1. **Khác biệt về bản chất vận hành**:
   - `news-scape` là **Ingestion Daemon** (tiến trình nền cào mạng sống 24/7, ghi CSDL runtime liên tục, gọi LLM suy luận ngữ nghĩa tốn token).
   - `fpa-toolkit` là **Quantitative Research Monorepo** (nền tảng nghiên cứu phục vụ hàng chục chuyên viên, yêu cầu kiểm thử hermetic offline, không phụ thuộc mạng ngoài, bảo đảm 100% xanh khi chạy CI).
2. **Xung đột quy chuẩn kiểm soát Git (Governance Invariants)**:
   - Monorepo có pre-commit hook `no-data-files` chặn đứng mọi file `.db`, `.parquet`, `.xlsx`, `.csv`. Nếu chuyển nguyên trạng CSDL `monocle.db` vào Monorepo, commit sẽ bị từ chối ngay lập tức.
   - Monorepo tuân thủ nghiêm ngặt **Universal English Core (`FFA-DEC-006`)**, cấm rò rỉ đường dẫn cá nhân (`no-workspace-paths`) và cấm attribution AI (`no-ai-attribution`).
3. **Nguy cơ quá tải Review (PR Reviewability Friction)**:
   - Nếu bê nguyên toàn bộ hàng chục ngàn dòng code của `news-scape` sang Monorepo, PR sẽ biến thành một "Mega-PR", gây quá tải cho Head of Research (`ducnn2`) và chắc chắn sẽ bị từ chối hoặc yêu cầu đập đi làm lại.

### 1.3. Question (Câu hỏi cốt lõi)
*Lựa chọn phương án kiến trúc nào để tích hợp tối đa giá trị của News-Scape vào Monorepo cho các chuyên viên FPTS khai thác thuận tiện nhất, vừa tuân thủ tuyệt đối quy chuẩn Monorepo, vừa giữ được tính gọn nhẹ để Pull Request được phê duyệt nhanh chóng?*

---

## 2. Khung "Optimizing For": Xác Định Thứ Tự Ưu Tiên Đánh Đổi

Theo khung tư duy của Nikita Miller, chúng ta phân định rõ mục tiêu nào là **bất biến phải tối ưu** và mục tiêu nào là **thỏa hiệp có kiểm soát**:

```
[BẤT BIẾN TỐI ƯU HÓA]
  ├─ 1. Khả năng được duyệt PR: PR gọn gàng, đúng phạm vi Epic 3, test xanh 100% offline.
  ├─ 2. Tính toàn vẹn Monorepo: Không đưa file dữ liệu nhị phân (.db, .parquet) vào Git.
  └─ 3. Trải nghiệm chuyên viên: Chuyên viên truy vấn tin tức dễ dàng qua UniversalHub.

[CHẤP NHẬN THỎA HIỆP CÓ KIỂM SOÁT]
  ├─ 1. Tách rời tiến trình cào mạng: Daemon cào tin chạy độc lập bên ngoài, không nhét vào Monorepo.
  └─ 2. Độ trễ cập nhật: Dữ liệu phân vùng theo batch định kỳ (1-2 giờ) thay vì streaming nano-giây.
```

---

## 3. Phân Tích Chi Tiết 3 Phương Án Tích Hợp

### PHƯƠNG ÁN A: Full Monolith Port (Chuyển Giao Toàn Bộ Vào Monorepo)
- **Mô hình**: Di dời toàn bộ thư mục `project/src/` của `news-scape` (crawler, scheduler, CSDL SQLite `monocle.db`, pipeline L1/Gold, preset DSH) vào một thư mục trong `fpa-toolkit` (như `shared/news/` hoặc `packages/news_scape/`).
- **Ưu điểm**:
  - Toàn bộ mã nguồn nằm tập trung tại một kho duy nhất.
  - Quản lý version control trên 1 Git repository.
- **Nhược điểm & Rủi ro chí mạng**:
  - 🔴 **Vi phạm pre-commit hooks nghiêm ngặt**: Hook `no-data-files` sẽ chặn file `monocle.db`, `.parquet`, `.xlsx`.
  - 🔴 **Làm gãy bộ kiểm thử tự động của Monorepo (Test Flakiness)**: Scraper phụ thuộc vào mạng Internet và cấu trúc DOM của bên thứ ba (CafeF, Vietstock). Khi các trang báo chặn IP/captcha hoặc đổi class HTML, bộ test `pytest` của toàn Monorepo sẽ bị ĐỎ, chặn đứng mọi commit của các chuyên viên FFA/FQS.
  - 🔴 **PR khổng lồ không thể review**: Hàng nghìn dòng code kèm CSDL sẽ bị `ducnn2` từ chối ngay tại cổng intake.

### PHƯƠNG ÁN B: Hybrid Data-Contract & UniversalHub Integration (Đề Xuất Tối Ưu)
- **Mô hình**:
  - **Tầng Thu thập & Tinh chế (News-Scape Service)**: Giữ `news-scape` là Ingestion Daemon độc lập chạy định kỳ trên máy trạm/server. Sau khi cào tin, bóc tách thực thể và tóm tắt, nó lưu trữ dữ liệu dạng **Parquet phân vùng chuẩn hóa** (`FRA - Data/news/year=YYYY/month=MM/articles.parquet`) và xuất các bản tin mẫu OKF Markdown vào SharePoint.
  - **Tầng Tiêu thụ & Tích hợp (FPA-Toolkit Monorepo)**: Chỉ tích hợp vào Monorepo bộ module không trạng thái (stateless) theo đúng đặc tả của **Epic 3**:
    1. `shared/news/scraper.py`: Engine cào & parse bài viết độc lập (hỗ trợ ad-hoc scraping và trích xuất HTML sạch).
    2. `shared/news/tagger.py`: Engine nhận diện Ticker qua `UniversalHub.get_all_tickers()` & sinh tóm tắt 3 bullets chuẩn văn phong tài chính khách quan.
    3. `shared/news/writer.py`: Generator xuất bản note OKF v0.2 và ghi nối Parquet phân vùng.
    4. `shared/data_ingestion/news_loader.py` (Gắn vào `UniversalHub.news`): Trình nạp tin tức Polars Lazy scan siêu tốc, hỗ trợ predicate pushdown theo `ticker`, `sector`, `date_range` tương tự `BCTCAnnualLoader` và `TradingLoader`.
- **Ưu điểm**:
  - 🟢 **100% Tuân thủ Governance**: Zero data files in Git, zero workspace leaks, 100% Universal English Core.
  - 🟢 **Khớp 100% Đặc tả Epic 3**: Triển khai chính xác phạm vi mà `ducnn2` đã phê duyệt trong lộ trình chung.
  - 🟢 **Trải nghiệm Chuyên viên Hoàn Hảo**: Chuyên viên FPTS không cần quan tâm đến cách cào tin hay chạy database phức tạp; họ chỉ cần gọi:
    ```python
    from shared.data_ingestion.data_hub import UniversalHub
    hub = UniversalHub()
    df_news = hub.news.get_articles(ticker="REE", start_date="2026-01-01")
    ```
  - 🟢 **PR Tinh Gọn, Khả Thi 100%**: Mã nguồn gói gọn ~600 dòng code sạch, có bộ test mock offline hoàn chỉnh, thời gian chạy test < 2 giây.
- **Nhược điểm & Đánh đổi**:
  - Cần duy trì daemon chạy nền ở repo `news-scape` hiện tại để liên tục bơm dữ liệu vào thư mục SharePoint `FRA - Data`.

### PHƯƠNG ÁN C: Satellite Package Pattern (Mô Hình Gói Vệ Tinh GLB-DEC-068)
- **Mô hình**: Đóng gói `news-scape` thành một package vệ tinh độc lập tại `packages/news_scape/` bên trong Monorepo, tương tự như gói `packages/ge_document_migration/`. Có `pyproject.toml` riêng, test colocated riêng, đồng bộ 2 chiều qua `shared.utils.satellite_sync`.
- **Ưu điểm**:
  - Tuân thủ pattern vệ tinh đã được Monorepo thiết lập sẵn.
  - Cô lập hoàn toàn dependencies và môi trường chạy.
- **Nhược điểm & Đánh đổi**:
  - 🟡 **Chi phí hạ tầng và vận hành quá cao (Over-engineering)**: Mô hình vệ tinh GLB-DEC-068 vốn được thiết kế cho các gói hợp tác với cộng tác viên bên ngoài để bảo vệ mã nguồn độc quyền FPTS. Đối với `news-scape` (do AnPT trực tiếp sở hữu nội bộ), việc duy trì cơ chế subtree merge và AST isolation là phức tạp không cần thiết.
  - 🟡 **Chưa giải quyết bài toán tiêu thụ dữ liệu**: Chuyên viên vẫn muốn có một accessor trực tiếp trên `UniversalHub` hơn là phải cài đặt một package vệ tinh.

---

## 4. Ma Trận Đánh Giá Đèn Giao Thông (Traffic Light Matrix — Naomi Gleit)

| Tiêu Chí Đánh Giá | Trọng Số | Phương Án A (Full Monolith) | Phương Án B (Hybrid Data-Contract) ⭐ | Phương Án C (Satellite Package) |
| :--- | :---: | :---: | :---: | :---: |
| **1. Khả năng Phê duyệt PR (Approval Friction)** | **25%** | 🔴 **ĐỎ** (Quá tải review, nguy cơ reject 95%) | 🟢 **XANH** (Gọn gàng, đúng 100% roadmap Epic 3) | 🟡 **VÀNG** (Cần thiết lập subtree sync) |
| **2. Độ Ổn Định & Tính Hermetic của Monorepo** | **20%** | 🔴 **ĐỎ** (Test fail khi web báo đổi DOM/chặn IP) | 🟢 **XANH** (Test offline hermetic dùng fixture) | 🟢 **XANH** (Có AST quarantine) |
| **3. Tuân Thủ Pre-commit Hooks & Data Hygiene** | **20%** | 🔴 **ĐỎ** (Bị chặn bởi hook `no-data-files`) | 🟢 **XANH** (Zero data files in git) | 🟢 **XANH** (Cô lập trong `packages/`) |
| **4. Trải Nghiệm Chuyên Viên (Analyst UX)** | **20%** | 🟡 **VÀNG** (Phải tự chạy pipeline cào tin) | 🟢 **XANH** (Truy vấn 1 dòng lệnh qua `UniversalHub`) | 🟡 **VÀNG** (Gọi qua CLI của package) |
| **5. Chi Phí Vận Hành & Bảo Trì Dài Hạn** | **15%** | 🔴 **ĐỎ** (Nghẽn Monorepo, khó refactor scraper) | 🟢 **XANH** (Độc lập: sửa scraper không ảnh hưởng core) | 🟡 **VÀNG** (Bảo trì subtree merge) |
| **KẾT LUẬN XẾP HẠNG** | **100%** | ❌ **LOẠI BỎ (Unviable)** | 🎯 **KHUYẾN NGHỊ CAO NHẤT (Top Pick)** | 🔄 **DỰ PHÒNG DÀI HẠN (Alternative)** |

---

## 5. Nhận Diện Các Cạm Bẫy Kỹ Thuật Ngầm (Surface Rabbit Holes — Ryan Singer)

Trước khi lập kế hoạch hành động, cần xác định rõ 3 cạm bẫy kỹ thuật tiềm ẩn của Phương án B:

1. **Cạm bẫy 1 — Đồng bộ Ticker Registry**:
   - `news-scape` hiện có từ điển ticker riêng. Nếu đưa vào Monorepo mà không đồng bộ với Master Ticker Registry của FPTS, các báo cáo phân tích chéo sẽ bị lệch mã.
   - *Biện pháp*: `shared/news/tagger.py` bắt buộc tích hợp với `UniversalHub.get_all_tickers()`.
2. **Cạm bẫy 2 — Xung đột File Lock Windows trên OneDrive ([`WinError 32`])**:
   - Khi daemon đang ghi dữ liệu hoặc chuyên viên đang mở file Excel, tiến trình nạp tin có thể crash do Windows file-locking.
   - *Biện pháp*: Tận dụng ngay tiện ích mới [`shared/utils/fs.py`](file:///C:/Users/anpt/Documents/fpa-toolkit/shared/utils/fs.py) (commit `c96b363` trưa 30/09), sử dụng `create_safe_snapshot()` và `read_excel_safe()`.
3. **Cạm bẫy 3 — Phụ thuộc Mạng Ngoài và API LLM Trong Unit Test**:
   - Nếu unit test gọi trực tiếp OpenRouter / Gemini API thật hoặc cào mạng thật, test sẽ bị chậm, tốn token và thất bại khi mất mạng.
   - *Biện pháp*: Mọi unit test trong `tests/shared/unit/test_news*.py` phải sử dụng **mock fixtures tĩnh**, bảo đảm test chạy trong < 2 giây và hermetic 100%.

---

## 6. Kết Luận Đề Xuất

**Lựa chọn dứt khoát Phương án B (Hybrid Data-Contract & UniversalHub Integration).**  
Phương án này tách biệt rõ ràng giữa **tiến trình sản xuất dữ liệu (News-Scape Daemon)** và **công cụ tiêu thụ dữ liệu (FPA-Toolkit Shared Module)**, mang lại giá trị cao nhất cho Khối Phân tích mà không tạo ra bất kỳ ma sát kỹ thuật nào cho Monorepo.
