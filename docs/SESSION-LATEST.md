# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-14
- **Current story:** US-014 (Ticker Tiering & Master Catalog Noise Elimination) — `implemented` (390/390 tests passed)
- **Status:** All test suites green (390/390 passed, 6/6 harness passed). 0 story `in_progress`.
- **Blocker:** Không còn blocker. Codebase hoàn toàn đồng bộ, sạch sẽ và an toàn.

## Việc đã làm phiên này (14/09/2026)

### 1. Thanh lọc & Phân tầng Danh mục TICKER 3 Tiers (US-014)
- **Hiện trạng trước thanh lọc**: `entities.json` nặng 1,5 MB chứa 2.153 thực thể (trong đó có 1.984 mã TICKER). Gần 45% danh mục là mã đã chết từ 10-15 năm trước hoặc siêu penny vô thanh khoản, gây ô nhiễm token và false positive với từ tiếng Việt.
- **Mô hình 3 Tiers triển khai**:
  - **Tier 1 (Core Universe — 742 mã)**: 100% Watchlist người dùng (`AnPT`, `PhoHG`, `ThanhTD`, `VyPTT`, `UyenNNT`) + doanh nghiệp lớn vốn hóa $\ge 300$ tỷ VND và đang hoạt động. Nhận diện bình thường qua mã 3 ký tự in hoa và alias thương hiệu.
  - **Tier 2 (Extended Universe — 351 mã)**: Doanh nghiệp vốn hóa 100 – 300 tỷ VND. Chỉ nhận diện qua mã khi là công bố thông tin đầu tiêu đề (`MÃ: ...`), trong văn bản thông thường bắt buộc nhận diện qua alias thương hiệu.
  - **Tier 3 (Archived / Dormant — 891 mã)**: Đã tách độc lập ra `data/entities/entities_archive.json` (731 KB). Loại bỏ 100% khỏi runtime `entities.json`.
- **Nâng cấp `build_entities.py`**:
  - Đọc `market_caps.parquet` và `users/*.yaml` để tự động tính `latest_date`, `market_cap_bil`, `is_active` và phân loại tier.
  - Xuất `entities.json` (giảm dung lượng còn 1.027 KB, -450 KB), `entities_archive.json`, `entities.csv` và `entities.xlsx` (bổ sung sheet `Archived_Securities`).
- **Nâng cấp Matcher `EntityRegistry` (`src/agent/entities.py`)**:
  - Bổ sung guard kiểm tra `ent_tier`: mã Tier 2 cô lập không bị bắt nhầm thành từ tiếng Việt thông dụng.
- **Kiểm định & Benchmark**:
  - Bổ sung unit test `project/tests/test_ticker_tiering.py` (PASS 100%).
  - Chạy full test suite: **390/390 passed**.
  - Benchmark trên 1.787 bài viết lịch sử: tốc độ nhận diện đạt **2.286 bài/giây** (0,78 giây cho toàn bộ dataset).

### 2. Thiết lập Mạng lưới Multi-Agent Swarm & Đóng gói 4 Specialized Skills
- **Xây dựng CLI Radar (`scripts/pipeline_radar.py`)**:
  - `pipeline_radar.py status`: Tự động quét DB và hàng đợi file, chỉ rõ bài viết đang ở điểm chạm nào (cào, L1, Gold, deliverable) và đề xuất chính xác lệnh PowerShell cần chạy tiếp theo.
  - `pipeline_radar.py token`: Giám sát ngân sách, đo lường lượng token thực tế và tỷ lệ tiết kiệm nhờ Subscriber-Gating (>91% chi phí tránh lãng phí).
  - `pipeline_radar.py users`: Tự động phát hiện khi có file đăng ký `*_news.xlsx` mới nhưng chưa khai báo trong `manifest.yaml`.
- **Đóng gói Hệ sinh thái Skills Chuyên Trách (`.agents/skills/`)**:
  - [pipeline-radar](file:///C:/Users/anpt/OneDrive%20-%20fpts.com.vn/FRA_DataIngestion%20-%20news-scape/.agents/skills/pipeline-radar/SKILL.md): Trinh sát điểm chạm dữ liệu, chỉ ra điểm nghẽn và lệnh xử lý tiếp theo.
  - [watchlist-curator](file:///C:/Users/anpt/OneDrive%20-%20fpts.com.vn/FRA_DataIngestion%20-%20news-scape/.agents/skills/watchlist-curator/SKILL.md): Quản trị người dùng, phát hiện file đăng ký mới, phân tầng Ticker 3 Tiers và đề xuất thực thể mới.
  - [token-auditor](file:///C:/Users/anpt/OneDrive%20-%20fpts.com.vn/FRA_DataIngestion%20-%20news-scape/.agents/skills/token-auditor/SKILL.md): Kiểm toán ngân sách token, theo dõi pruning payload $\le 2.200$ ký tự và cảnh báo chi phí.
  - [dod-gatekeeper](file:///C:/Users/anpt/OneDrive%20-%20fpts.com.vn/FRA_DataIngestion%20-%20news-scape/.agents/skills/dod-gatekeeper/SKILL.md): Gác cổng kiểm định chất lượng, bắt lỗi grounded substring, chống trùng lặp key_points và tự sửa System Prompt.
### 4. Chuẩn Hóa Mẫu Prompt Mồi Vận Hành Ngày Mới (Daily Trigger Template)
- **Chuẩn hóa Prompt Mẫu 2**:
  > *"Bắt đầu phiên ngày {YYYY-MM-DD}: Hãy dùng Radar kiểm tra điểm chạm pipeline, sau đó thực thi trọn vẹn chuỗi L1 (vật chất hóa Code-First trước để tiết kiệm token, phần còn lại gom mini-batches cho Subagents Flash xử lý có kiểm soát). Báo cáo tỷ lệ DoD và tổng lượng token tiêu thụ sau khi hoàn tất."*
- **Tích hợp sâu vào 3 Skills**:
  - `pipeline-radar/SKILL.md`: Mục 5 đặc tả chuỗi 6 bước phản xạ tự động của Agent.
  - `multi-agent-orchestrator-governance/SKILL.md`: Mục 4 Runbook hàng ngày.
  - `news-scape-agent-operations/SKILL.md`: Mục 2 Bước 0 làm điểm kích hoạt chuẩn.

## Next Steps
1. Sẵn sàng nhận lệnh kích hoạt chuỗi L1 cho ngày mới **15/09/2026** (hiện có 176 bài cào mới đang đợi).
2. Duy trì quy chuẩn tiết kiệm token tối đa và kiểm soát rủi ro qua Controlled Waves.

