# ADR 0011 — Tích hợp Antigravity CLI (`agy`) runner và bộ điều phối headless cho Article Lane

- **Ngày:** 2026-09-25
- **Trạng thái:** **accepted**. Người dùng duyệt ngày 2026-09-25 (triển khai theo kết luận hội đồng thẩm định kiến trúc 2026-09-23 và kế hoạch US-028).
- **Lane:** **high-risk**, vì chạm automation substrate, bổ sung cognitive runner mới và cơ chế trigger chạy nền.
- **Story:** US-028 (Runner `agy`, Sandboxed Worker Profile, CLI `--runner agy`, trigger `article_tick.py`)
- **Kế thừa & Phát triển:** [ADR 0010](0010-ngung-lane-l1-gold-article-lane-duy-nhat.md) (Article Lane duy nhất, token là ghi nhận không phải cổng), kế thừa kết quả thực nghiệm tại [`docs/proposals/agy-automation-council-2026-09-23.md`](../proposals/agy-automation-council-2026-09-23.md).

---

## 1. Bối cảnh

Từ ngày 2026-09-23 (ADR 0010), Article Lane là đường xử lý duy nhất của News-Scape. Quá trình phân tích nhận thức được thực thi bởi agent `article-processor` thông qua giao diện DeepSeek Harness (DSH). Tuy nhiên, môi trường DSH bộc lộ các hạn chế lớn đối với mục tiêu vận hành tự động hoá doanh nghiệp:

1. **Thiếu khả năng chạy không giám sát (Headless Incompatibility)**: DSH Conductor chạy trong trình duyệt web, đòi hỏi người vận hành sao chép và dán chương trình TypeScript (`wave_<W>.conductor.ts`) vào môi trường `run_code`. Không thể lập lịch tự động định kỳ vào các khung giờ thị trường (07:30, 12:30, 15:30, 17:30).
2. **Hạn chế quyền ghi tập tin (Sandbox WritableRoots)**: Sandbox của DSH chỉ cho phép ghi tập tin bên trong thư mục kho mã hoặc thư mục tạm, trong khi cơ sở dữ liệu sản xuất nằm tại `C:\data\news-scape\monocle.db` để tránh xung đột đồng bộ OneDrive.
3. **Hiện tượng nạp cấu hình lúc mount (Rule 09)**: DSH nạp preset lúc khởi động tiến trình host, nếu có cập nhật cấu hình mà không khởi động lại máy chủ sẽ dẫn đến sai lệch ngầm.
4. **Đặc thù gói Subscription Antigravity**: Dự án sử dụng tài khoản Antigravity trả phí (pool "Work Done" làm mới mỗi 5 giờ). Tài khoản này không tính phí theo từng token riêng lẻ mà quản trị theo hạn mức phiên, cho phép phân tích trọn vẹn toàn bộ bài báo mà không lo phát sinh chi phí biến đổi vượt tầm kiểm soát.

---

## 2. Quyết định

1. **Dual-Runner Article Lane**:
   - Bổ sung runner `agy` (sử dụng mô hình `gemini-3.8-flash-low`) hoạt động song song với runner mặc định `dsh` (`deepseek-flash`).
   - Phân công: `dsh` tiếp tục phục vụ các phiên làm việc tương tác có người giám sát; `agy` đảm nhận các đợt chạy tự động không giám sát (headless automation).
2. **Nguyên tắc Hàm Nhận thức Thuần (Stateless Pure Cognitive Function)**:
   - Python giữ vai trò điều phối viên (Conductor, 0 token, tất định).
   - `agy` chỉ đóng vai trò hàm nhận thức một lượt (Single-turn, prompt-in / JSON-out), **không được cấp bất kỳ công cụ nào** (`tools: []`). Triệt tiêu 100% rủi ro prompt injection và các lỗi tiến trình nền (#1044, #902).
3. **Cô lập Bằng Sandboxed Worker Profile**:
   - Mỗi đợt chạy tự động sinh một hồ sơ làm việc độc lập tại `%LOCALAPPDATA%\news-scape\agy_profiles\<wave>\`.
   - Cấu hình rỗng `permissions.allow: []`, không kế thừa quyền chạy lệnh shell của người dùng chính.
   - Nạp Custom Agent toàn cục với `excludeDefaultComponents: true`, body nhúng nguyên văn [`project/data/prefix/ARTICLE_SYSTEM_CORE.md`](../../project/data/prefix/ARTICLE_SYSTEM_CORE.md). Giảm 45% token overhead cố định mà không cần cắt bớt nội dung bài báo.
   - Bổ sung hook `PreToolUse` từ chối mọi yêu cầu gọi tool bất thường.
4. **Giao thức Nhập/Xuất Dữ liệu**:
   - Dữ liệu bài viết truyền qua stdin định dạng `stream-json` (NDJSON 1 dòng) để vượt qua giới hạn độ dài dòng lệnh Windows (32.767 ký tự).
   - **Tuyệt đối không dùng cờ `--json-schema`** (vì agy hiện thực schema bằng tool ẩn `finish`, xung đột với cấu hình `tools: []`). Python đảm nhận bóc tách kết quả bằng `salvage_records`, kiểm định JSON Schema và kiểm tra miền nghiệp vụ (11 mã nhóm, dấu tiếng Việt, dải chỉ số trích dẫn).
5. **Tuyệt đối Không Sử dụng Trần Token**:
   - Bác bỏ mọi đề xuất về trần token theo ngày, trần từ hay giới hạn ký tự làm cắt xén bài viết hoặc ngắt đợt xử lý của agent.
   - Token chỉ ghi nhận vào sổ cái `token_ledger` và tệp metadata để kiểm toán ROI và hiệu năng.
   - Kích thước lô cố định 50 bài/lô đối với `agy` nhằm tối ưu hóa độ ổn định mạng và thời gian phản hồi.
6. **Bộ Điều Phối Headless & Cơ Chế Kích Hoạt Kép (Hybrid Trigger)**:
   - Script điều phối `scripts/article_tick.py` được lập lịch định kỳ qua Windows Task Scheduler.
   - Điều kiện kích hoạt: Mở đợt khi số bài chờ phân tích $\ge 50$ bài (Fast Path) **hoặc** khi chạm các khung giờ chốt phiên thị trường (07:30, 12:30, 15:30, 17:30).
   - Quản trị an toàn: Khóa đơn tiến trình `.pipeline.lock` tại `C:\data\news-scape\`, cờ dừng khẩn cấp `AGY_STOP` tại `C:\data\news-scape\`.

---

## 3. Hệ quả

- `article_run.py` hỗ trợ tham số `--runner {dsh,agy}` và cờ `--analyze` tự động hóa cho `agy`.
- `article_expand.py` tự động nhận diện provenance từ tệp metadata (`agent_provider="agy"`, `model="gemini-3.8-flash-low"`).
- Dữ liệu nạp vào cơ sở dữ liệu `monocle.db` tuân thủ 100% Data Contract hiện hành qua hai cổng DoD `l1_ingest` và `agent_ingest`.
- Quản trị nhịp độ (Pacing): Xử lý tối đa 100 bài (2 lô $\times$ 50 bài) mỗi đợt để không gây nghẽn hạn mức phiên 5 giờ của tài khoản Antigravity.

---

## 4. Quay lui

Nếu runner `agy` phát sinh lỗi kỹ thuật hoặc tỷ lệ vượt cổng DoD $< 90\%$ trong hai đợt liên tiếp:
- Người vận hành chỉ cần tạo tệp cờ `C:\data\news-scape\AGY_STOP` để tạm dừng bộ kích hoạt ngầm.
- Hệ thống tiếp tục vận hành bình thường thông qua runner mặc định `dsh` bằng lệnh `article_run.py --runner dsh`. Toàn bộ dữ liệu Silver và mã nguồn lõi không bị ảnh hưởng.
