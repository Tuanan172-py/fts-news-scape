# Kế Hoạch Chi Tiết: Tích Hợp Hệ Thống News-Scape Vào FPA Toolkit Monorepo

- **Ngày lập:** 2026-10-01
- **Trạng thái:** Kế hoạch thực thi chi tiết (Execution Blueprint) — **Giai đoạn chuẩn bị, chưa viết mã nguồn (No-Code Phase)**.
- **Phương án lựa chọn:** **Phương án B — Hybrid Data-Contract & UniversalHub Integration** (xem chi tiết tại [`research_tradeoffs.md`](research_tradeoffs.md)).
- **Chủ trì kế hoạch:** Phạm Thành An (`anpt` / `FTA1`)
- **Reviewer & Phê duyệt:** Nguyễn Ngọc Đức (`ducnn2` / Head of Research)
- **Căn cứ kế hoạch:** [`EPIC-03-ai-news-scanner.md`](file:///C:/Users/anpt/Documents/fpa-toolkit/docs/GE_rollout/epics/EPIC-03-ai-news-scanner.md), [`monorepo_master_roadmap.md`](file:///C:/Users/anpt/Documents/fpa-toolkit/docs/governance/monorepo_master_roadmap.md), [`GLB-DEC-061`](file:///C:/Users/anpt/Documents/fpa-toolkit/shared/utils/fs.py)

---

## 1. Tuyên Ngôn Phạm Vi & Nguyên Tắc "No-Code" Giai Đoạn Này

> [!IMPORTANT]
> **TUYÊN NGÔN GIAI ĐOẠN (NO-CODE INVARIANT)**:
> - Tại phiên làm việc này, hệ thống **tuyệt đối KHÔNG viết mã nguồn triển khai** (`.py`).
> - Trọng tâm của phiên là: Nghiên cứu, đánh giá các phương án đánh đổi, thiết lập kiến trúc hợp đồng dữ liệu, và xây dựng bản kế hoạch chi tiết từng bước (WBS) để khi bước sang giai đoạn code, mọi thao tác đều chuẩn xác, vượt qua 100% cổng kiểm tra chất lượng và không gây xung đột với Monorepo.

---

## 2. Mục Tiêu Chiến Lược & Kết Quả Bàn Giao Cốt Lõi

1. **Nghiệm thu hoàn tất [Epic 3](file:///C:/Users/anpt/Documents/fpa-toolkit/docs/GE_rollout/epics/EPIC-03-ai-news-scanner.md)**: Đưa toàn bộ các thành phần thu thập, bóc tách thực thể, xuất bản OKF Markdown và lưu trữ Parquet vào `fpa-toolkit` đúng ranh giới được giao.
2. **Tuân thủ 100% Quản trị Monorepo**: Đạt 100% Universal English Core, zero data files trong Git (`no-data-files`), zero workspace paths rò rỉ (`no-workspace-paths`), không rò rỉ attribution AI (`no-ai-attribution`).
3. **Mở rộng năng lực UniversalHub (Giai đoạn sau Merge)**: Cho phép mọi chuyên viên FPTS và các AI Agent gọi dữ liệu tin tức bằng 1 dòng lệnh:
   ```python
   hub.news.get_articles(ticker="REE", start_date="2026-01-01")
   ```
4. **Vận hành Độc lập cho Ingestion Daemon**: Daemon cào tin sống của `news-scape` tiếp tục chạy độc lập, tự động bơm dữ liệu Parquet phân vùng vào `FRA - Data/news/`.

---

## 3. Phân Rã Công Việc Từng Giai Đoạn (Work Breakdown Structure - WBS)

```
[Phase 0: Chuẩn bị Môi trường & Git] ──► [Phase 1: Đặc tả Module Lõi shared/news/]
                                                           │
                                                           ▼
[Phase 3: Cổng Kiểm Soát Chất Lượng] ◄── [Phase 2: Bộ Unit Test Hermetic]
               │
               ▼
[Phase 4: Đóng Gói Commit & Mở PR] ────► [Phase 5: Hậu Hợp Nhất & UniversalHub]
```

---

### PHASE 0: Chuẩn Bị Môi Trường Máy Trạm & Hạ Tầng Git (Pre-flight Setup)

*Mục tiêu: Đưa máy trạm về trạng thái 100% compliant với 11 trụ cột onboarding và tạo nhánh Git sạch từ `origin/main`.*

- [ ] **Task 0.1 — Chuẩn hóa Vị trí Thư mục Repo**:
  - Kiểm tra vị trí `C:\Users\anpt\Documents\fpa-toolkit`.
  - Khuyến nghị di chuyển (hoặc clone) sang `$HOME\fpa-toolkit` (`C:\Users\anpt\fpa-toolkit`) theo chuẩn [`GLB-DEC-038`](file:///C:/Users/anpt/Documents/fpa-toolkit/docs/adr/GLB-DEC-038-sharepoint-workspace-junction-and-external-repo-clone.md) để tránh xung đột file-lock của OneDrive.
- [ ] **Task 0.2 — Thiết lập Conda Environment `fpa-toolkit` (Python 3.11)**:
  - Chạy `conda create -y -n fpa-toolkit python=3.11`.
  - Cài đặt gói: `pip install -r requirements.txt`, `pip install -e .`, `pip install -e ".[dev]"`.
  - Cài đặt Git hooks: `pre-commit install`.
- [ ] **Task 0.3 — Khởi tạo 2 NTFS Directory Junctions**:
  - Chạy `setup_workspace.ps1` với tham số `-AccountName 'anpt' -Team 'fta' -Role 'Technical & Big Data Analyst'`.
  - Xác nhận liên kết 2 Junctions:
    1. `fta/workspaces/anpt` $\rightarrow$ OneDrive container cá nhân.
    2. `sharepoint/` $\rightarrow$ OneDrive container kết nối tới `FRA - Data`.
- [ ] **Task 0.4 — Kiểm toán 11 Trụ Cột Onboarding**:
  - Chạy `setup_workspace.ps1 -Audit`.
  - **Điều kiện dừng**: Tất cả 11 trụ cột phải đạt trạng thái `[PASS]`.
- [ ] **Task 0.5 — Tạo Nhánh Tính Năng Sạch Từ Remote (`origin/main`)**:
  - Chạy `git fetch origin`.
  - Chạy `git checkout -b feat/epic-03-news-scanner origin/main`.
  - Xác nhận commit cơ sở là `a381c67` (bản mới nhất của `ducnn2`), loại bỏ hoàn toàn 194 commit diverged của nhánh `main` cục bộ trước đó.

---

### PHASE 1: Đặc Tả Module Lõi `shared/news/` (Core Engines Specification)

*Mục tiêu: Thiết kế chi tiết giao diện (interface), kiểu dữ liệu và hợp đồng hoạt động của 3 tệp lõi theo chuẩn Universal English Core.*

- [ ] **Task 1.1 — Đặc tả `shared/news/scraper.py`**:
  - **Class**: `NewsScraper`
  - **Phương thức chính**:
    - `fetch_article(url: str) -> dict`: Trích xuất `title`, `body_text`, `author`, `publish_time`, `source_domain`.
    - `fetch_rss(feed_url: str) -> list[dict]`: Lấy danh sách bài viết mới từ RSS portal.
    - `_canonicalize_url(url: str) -> str`: Chuẩn hóa URL, loại bỏ tracking param (`utm_*`).
    - `_compute_content_hash(text: str) -> str`: Tạo mã SHA-256 chống bài viết trùng lặp.
  - **Ràng buộc**: Throttling lịch sự (polite backoff delay 1.0–2.0s), timeout an toàn 10s.
- [ ] **Task 1.2 — Đặc tả `shared/news/tagger.py`**:
  - **Class**: `NewsTagger`
  - **Phương thức chính**:
    - `extract_tickers(text: str) -> list[str]`: Quét token mã cổ phiếu (sử dụng regex `[A-Z0-9]+` theo quy chuẩn cổ phiếu VN), đối chiếu với `UniversalHub.get_all_tickers()`.
    - `classify_sector(ticker: str) -> str`: Ánh xạ ngành theo danh mục phân ngành chuẩn FPTS.
    - `generate_digest(text: str, max_bullets: int = 3) -> list[str]`: Tạo 3 luận điểm tóm tắt cô đọng bằng tiếng Việt, tuân thủ kỷ luật Unslop (loại bỏ sáo ngữ AI: "bức tranh toàn cảnh", "cách mạng hóa", "hứa hẹn").
- [ ] **Task 1.3 — Đặc tả `shared/news/writer.py`**:
  - **Class**: `NewsWriter`
  - **Phương thức chính**:
    - `emit_okf_note(article_meta: dict, output_dir: Path) -> Path`: Xuất bản file Markdown chuẩn OKF v0.2 frontmatter (`uuid`, `type: News Digest`, `tier: 2`, `ticker`, `sector`, `source_url`, `timestamp`).
    - `append_parquet(article_data: dict, parquet_root: Path) -> Path`: Ghi nối bài viết vào Parquet phân vùng theo thời gian (`year=YYYY/month=MM/articles.parquet`) bằng `pyarrow` / `polars`.
    - Tích hợp hàm `create_safe_snapshot` từ `shared.utils.fs` để bảo vệ tiến trình đọc/ghi không bị lỗi lock file trên Windows.
- [ ] **Task 1.4 — Đặc tả Thư mục Mẫu OKF tại `shared/okf_base/news/`**:
  - Tạo cấu trúc thư mục `shared/okf_base/news/templates/`.
  - Cung cấp ít nhất 2 tệp mẫu OKF hợp lệ cho ngành Ngân hàng (`VCB`) và Thép (`HPG`).

---

### PHASE 2: Thiết Kế Bộ Kiểm Thử Đơn Vị Hermetic (Unit Test Design)

*Mục tiêu: Xây dựng bộ test hermetic chạy offline 100%, không gọi mạng thật, không gọi LLM API thật, thực thi dưới 3 giây.*

- [ ] **Task 2.1 — Tạo Mock Fixtures Tĩnh (`tests/shared/fixtures/news_mock/`)**:
  - Lưu trữ 3 đoạn HTML mẫu rút gọn từ CafeF, Vietstock, NDH.
  - Mock danh sách Ticker trả về từ `UniversalHub` (chứa `VCB`, `BID`, `HPG`, `FPT`, `REE`).
- [ ] **Task 2.2 — Thiết kế Ca Kiểm Thử `tests/shared/unit/test_news_scraper.py`**:
  - `test_extract_article_fields`: Xác nhận bóc tách đủ title, content, publish_time.
  - `test_url_canonicalization`: Xác nhận xóa bỏ query parameters rác (`utm_source`, `ref`).
  - `test_deduplication_hash`: Xác nhận 2 bài viết cùng nội dung sinh ra cùng một mã hash.
- [ ] **Task 2.3 — Thiết kế Ca Kiểm Thử `tests/shared/unit/test_news_tagger.py`**:
  - `test_ticker_extraction`: Khớp chính xác mã có trong registry, bỏ qua token nhiễu.
  - `test_digest_bullets_format`: Tóm tắt trả về đúng danh sách 3 gạch đầu dòng, không rỗng.
- [ ] **Task 2.4 — Thiết kế Ca Kiểm Thử `tests/shared/unit/test_news_writer.py`**:
  - `test_emit_okf_frontmatter`: Tệp Markdown sinh ra parse được YAML frontmatter, đủ các trường bắt buộc.
  - `test_parquet_partition_structure`: Tệp Parquet được ghi đúng đường dẫn `year=YYYY/month=MM/` và đọc lại bằng Polars không bị lỗi schema.

---

### PHASE 3: Quy Trình Kiểm Định Cổng Nghiệm Thu Cục Bộ (Quality Gates SOP)

*Mục tiêu: Đảm bảo 100% cổng kiểm soát chất lượng của Monorepo đều bật XANH trước khi thực hiện commit.*

- [ ] **Gate 3.1 — Kiểm Tra Cú Pháp AST**:
  ```powershell
  python -c "
  import ast, glob
  for f in glob.glob('shared/news/**/*.py', recursive=True) + glob.glob('tests/shared/unit/test_news*.py'):
      ast.parse(open(f, encoding='utf-8').read())
  print('AST check passed 100%')
  "
  ```
- [ ] **Gate 3.2 — Chạy Pytest Scoped (Fail-Fast)**:
  ```powershell
  python -m pytest tests/shared/unit/test_news_scraper.py -x -v
  python -m pytest tests/shared/unit/test_news_tagger.py -x -v
  python -m pytest tests/shared/unit/test_news_writer.py -x -v
  ```
- [ ] **Gate 3.3 — Kiểm Tra Tính Toàn Vẹn Tài Liệu & Link Markdown**:
  ```powershell
  python -m pytest tests/test_docs_integrity.py -x
  ```
- [ ] **Gate 3.4 — Chạy Tự Động Hóa Wrapup Runner**:
  ```powershell
  python -m shared.utils.wrapup_runner
  ```
- [ ] **Gate 3.5 — Kiểm Định Toàn Bộ Pre-Commit Hooks**:
  ```powershell
  pre-commit run --all-files
  ```
  *(Đảm bảo không có lỗi `no-data-files`, `no-workspace-paths`, `no-ai-attribution`).*

---

### PHASE 4: Quy Trình Đóng Gói Commit & Mở Pull Request (PR Protocol)

*Mục tiêu: Đóng gói commit chuẩn và tạo Pull Request chuyên nghiệp theo mẫu nghiệm thu của Khối Phân tích.*

- [ ] **Task 4.1 — Selective Staging**:
  - Thực hiện stage đích danh:
    ```powershell
    git add shared/news/
    git add shared/okf_base/news/
    git add tests/shared/unit/test_news*.py
    ```
- [ ] **Task 4.2 — Conventional Commit**:
  - Đặt thông điệp commit chuẩn:
    ```powershell
    git commit -m "feat(news): implement financial news scanner, entity tagger and okf writer (EPIC-03)"
    ```
- [ ] **Task 4.3 — Đồng Bộ Trước Khi Push**:
  - Chạy `git fetch origin` và `git rebase origin/main`.
  - Đẩy nhánh: `git push -u origin feat/epic-03-news-scanner`.
- [ ] **Task 4.4 — Tạo Pull Request Trên GitHub**:
  - Truy cập `https://github.com/Research-FPA/fpa-toolkit/pulls`.
  - Base: `main` $\leftarrow$ Compare: `feat/epic-03-news-scanner`.
  - Tiêu đề: `feat(news): implement AI news scanner & big data ingestion pipeline (Epic 3)`.
  - Gắn Reviewer: `ducnn2`.
  - Dán nội dung mô tả PR theo đúng mẫu tại Phần 6.2 của hướng dẫn tích hợp.

---

### PHASE 5: Kế Hoạch Hậu Hợp Nhất (Post-Merge Roadmap)

*Mục tiêu: Đưa dữ liệu tin tức vào phục vụ rộng rãi toàn bộ chuyên viên FPTS và kích hoạt Ingestion Daemon tự động.*

- [ ] **Task 5.1 — Tích Hợp Facade `UniversalHub.news`**:
  - Xây dựng lớp `NewsLoader` tại `shared/data_ingestion/news_loader.py` sử dụng Polars predicate pushdown.
  - Gắn vào `UniversalHub`:
    ```python
    self.news = NewsLoader(self.fra_data_root)
    ```
- [ ] **Task 5.2 — Cập Nhật Kỹ Năng Tra Cứu Dữ Liệu (`.agents/skills/load-data/`)**:
  - Bổ sung domain `news` vào `catalog_hub_matrix.md` và `code_recipes.md` để các AI Agent trong Monorepo biết cách gọi dữ liệu tin tức.
- [ ] **Task 5.3 — Tự Động Hóa Daemon News-Scape**:
  - Cấu hình tiến trình daemon tại repo `news-scape` tự động xuất dữ liệu phân vùng vào thư mục mount `FRA - Data/news/`.

---

## 4. Ma Trận Quản Trị Rủi Ro & Kế Hoạch Dự Phòng

| Rủi Ro Nhận Diện | Khả Năng | Tác Động | Biện Pháp Phòng Vệ Chủ Động | Kế Hoạch Dự Phòng |
| :--- | :---: | :---: | :--- | :--- |
| **Xung đột file-lock trên Windows/OneDrive** | Cao | Cao | Sử dụng `create_safe_snapshot()` từ `shared.utils.fs` ngay từ thiết kế ban đầu. | Fallback sang ghi tạm tại local scratch nếu OneDrive bị nghẽn. |
| **Pre-commit hook chặn file dữ liệu** | Trung bình | Nghiêm trọng | Cấu hình test chỉ dùng dummy in-memory DataFrame hoặc thư mục `tmp_path` của pytest. | Không bao giờ tạo file `.parquet` cố định trong code tree. |
| **Reviewer (`ducnn2`) yêu cầu sửa đổi scope** | Thấp | Trung bình | Bám sát 100% bảng giao việc của `EPIC-03-ai-news-scanner.md`. | Tạo các commit nhỏ `fix(news): ...` trực tiếp trên nhánh PR. |

---

## 5. Tiêu Chí Nghiệm Thu Hoàn Thành (Definition of Done - DoD)

Một công việc chỉ được đánh dấu là hoàn thành khi đáp ứng đủ 6 tiêu chí:

1. [ ] Cấu trúc thư mục `shared/news/` và `shared/okf_base/news/` được tạo lập đầy đủ và tuân thủ Universal English Core.
2. [ ] Bộ 3 unit test trong `tests/shared/unit/` đạt tỷ lệ **PASS 100%** khi chạy độc lập offline (`pytest tests/shared/unit/test_news*.py -x`).
3. [ ] Không có bất kỳ file `.db`, `.parquet`, `.xlsx`, `.csv` nào nằm trong staging area của Git.
4. [ ] Lệnh `pre-commit run --all-files` vượt qua toàn bộ các hooks mà không có cảnh báo.
5. [ ] Lệnh `python -m shared.utils.wrapup_runner` kết thúc với `exit code 0`.
6. [ ] Pull Request được tạo trên GitHub với mô tả chi tiết, liên kết tới Epic 3 và gắn reviewer `ducnn2`.
