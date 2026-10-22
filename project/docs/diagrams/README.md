# Sơ đồ vận hành news-scape

Bộ sơ đồ toàn bộ quy trình vận hành, đọc được trên máy local, không cần mạng (ADR-0026, US-048). Logic lấy từ [`../design/00-end-to-end-architecture.md`](../design/00-end-to-end-architecture.md); khi mâu thuẫn, tài liệu đó thắng.

## Cách xem

Mở `index.html` bằng trình duyệt (nhấp đúp). Đó là một tệp duy nhất, tự chứa, trình bày theo dạng tài liệu nghiên cứu: tóm tắt, bản đồ tương tác sáu lớp (Hình 1), sáu bảng (hệ thống, lớp, kho dữ liệu, bất biến, quyết định, việc còn mở) và 16 sơ đồ chi tiết (Hình 2 đến Hình 17). Không cần mạng; gửi riêng tệp này cho người khác vẫn xem được. In bằng Ctrl+P ra khổ A4 ngang, hoặc dùng nút "In hoặc lưu PDF".

Các tệp `.mmd` là nguồn của mục "Sơ đồ chi tiết"; không cần mở riêng chúng.

## Mục lục

| Tệp | Nội dung |
|-----|----------|
| `00-context.mmd` | C4 mức 1: người, nguồn tin, runner LLM, SharePoint |
| `01-containers.mmd` | C4 mức 2: sáu lớp và các kho dữ liệu |
| `10`–`15` | Một sơ đồ cho mỗi lớp: L0 điều khiển, L1 thu thập, L2 Silver, L3 Article Lane, L4 Lakehouse, L5 Harness |
| `20-flow-main.mmd` | Dòng dữ liệu chính từ nguồn tới chuyên viên |
| `21-flow-wave.mmd` | Vòng đời một wave do daemon mở |
| `22-flow-capture.mmd` | Thu thập trọn vẹn và đối soát |
| `23-flow-publish.mmd` | Xuất bản: `publish.py` → `publish_day()` |
| `24-flow-delivery.mmd` | Giao Excel, manifest người dùng, cây `users/output` |
| `25-flow-session-close.mmd` | Đóng phiên harness, ghi nhận không chặn |
| `30-state-levels.mmd` | Mức tự chủ L0/L1 |
| `31-runner-order.mmd` | Thứ hạng runner: agy, `opencode run`, OpenRouter |

## Quy ước

- Chuẩn trình bày lấy từ bộ `report_writing_skills` (báo cáo HTML học thuật, văn phong tài liệu doanh nghiệp), chắt lọc cho tài liệu vận hành: một giao diện sáng, đơn sắc (đen, xám, trắng), chữ serif cho nội dung, chữ sans cho bảng và chú thích, bảng kiểu booktabs, hình và bảng đánh số liên tục với chú thích đặt ngay dưới hình (tiêu đề bảng đặt trên bảng).
- Không dùng emoji, ký hiệu trang trí, nhãn màu dạng pill, thẻ KPI bo góc, chuỗi mảnh câu nối bằng dấu chấm giữa hoặc mũi tên, và các cụm cường điệu. `tests/test_diagrams.py` kiểm các điều này trong `map.template.html`.
- Phân biệt bằng hình dạng và kiểu nét, không bằng màu: nét liền là dòng dữ liệu, nét đứt là điều khiển, nét chấm là đọc, nét chấm gạch là quản trị. Trong sơ đồ Mermaid, khung nét đứt là cổng kiểm tra, khung đậm là kết quả đạt, khung nét chấm là lỗi hoặc điều bị cấm, nền xám là kho dữ liệu hoặc hệ ngoài.
- `map.template.html` giữ nội dung bản đồ, các bảng và văn bản; sửa ở đó. Các tệp `*.mmd` là sơ đồ chi tiết; dòng đầu `%% title:` và `%% desc:` cấp tiêu đề và chú thích hình.
- Sửa xong chạy `python scripts/docs/build_diagrams.py` từ thư mục `project/` để dựng lại `index.html`. `--check` chỉ kiểm tệp có lỗi thời không.
- Nhãn Mermaid chứa ký tự đặc biệt phải bọc ngoặc kép; dùng `flowchart`, không dùng `graph`; cổng kiểm tra là hình chữ nhật có `class gate` thay vì hình thoi để sơ đồ không phình to.
- Tên tệp trong khối `files:[...]` của bản đồ và trong nhãn `.mmd` phải tồn tại trong repo; `tests/test_diagrams.py` kiểm điều này.
- Dùng Cambria hoặc Times New Roman cho chữ serif vì Georgia không có glyph xếp chồng dấu tiếng Việt. Không tải font từ mạng.
- `vendor/mermaid.min.js` được ghim phiên bản (xem `vendor/VERSION.txt`) và nhúng thẳng vào `index.html`; không đổi sang CDN.
- Khi mâu thuẫn, [`../design/00-end-to-end-architecture.md`](../design/00-end-to-end-architecture.md) thắng.
