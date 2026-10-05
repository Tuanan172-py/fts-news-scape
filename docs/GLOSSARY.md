# Bảng thuật ngữ

- **Loại tài liệu:** tham chiếu (reference, theo Diátaxis).
- **Phạm vi:** toàn bộ tài liệu, giao diện và tin nhắn của dự án News-Scape.
- **Nguyên tắc:** một khái niệm một tên. Tài liệu mới dùng tên chuẩn ở cột đầu; tên cũ chỉ còn trong lịch sử ADR và tên tệp.
- **Cập nhật:** 2026-10-01.

## 1. Khung vận hành (harness)

| Thuật ngữ | Nghĩa |
|---|---|
| **Harness** | Mô hình vận hành của kho mã, biến ý định thành thay đổi an toàn và có bằng chứng. Không phải mã sản phẩm. |
| **Chính sách (policy)** | Tài liệu markdown mô tả cách làm việc. Ổn định, người đọc được. |
| **Durable** | Cơ sở dữ liệu ghi lại điều đã xảy ra (intake, story, trace) trong `harness.db`, thao tác bằng `scripts/harness_cli.py`. |
| **OKF** | Tệp tri thức vận hành: nguồn ngữ cảnh sản phẩm cần đọc trước khi suy diễn. Xem [AGENTS.md](../AGENTS.md). |
| **Loại yêu cầu** | Cổng quyền hạn: chỉ đọc (trả lời, giải thích, chẩn đoán, lập kế hoạch) hoặc thay đổi (xây, sửa, áp dụng). Quyết định theo kết quả mong muốn, không theo từ khoá. |
| **Intake** | Bước phân loại một yêu cầu thay đổi vào một làn rủi ro trước khi làm. Xem [FEATURE_INTAKE.md](FEATURE_INTAKE.md). |
| **Làn rủi ro** | `tiny`, `normal` hoặc `high-risk`: mức công sức và soát xét của một thay đổi, đặt theo số cờ rủi ro. |
| **Hard Gate** | Cờ rủi ro buộc làn `high-risk` và một quyết định của người, ví dụ đổi lược đồ DB hoặc bí mật. |
| **Story** | Đơn vị công việc `US-XXX` có hợp đồng, tiêu chí nghiệm thu và bằng chứng. Khuôn: [templates/story.md](templates/story.md). |
| **Bằng chứng (proof)** | Kết quả máy đọc được của một lệnh kiểm tra, dùng để chứng minh một khẳng định. Không có bằng chứng thì chưa implemented. Xem [TEST_MATRIX.md](TEST_MATRIX.md). |
| **Trace (harness)** | Bản ghi phiên làm việc: việc đã làm, tệp đã đọc và sửa, kết cục, ma sát. Khác với *vết* ở mục 4. |
| **Bàn giao (handoff)** | Bước cuối của vòng thay đổi: ghi đè [SESSION-LATEST.md](SESSION-LATEST.md) để phiên sau biết đang ở đâu và làm gì tiếp. |
| **Ma sát (friction)** | Một khó khăn hoặc thiếu sót cụ thể gặp khi làm việc, ghi vào [HARNESS_BACKLOG.md](HARNESS_BACKLOG.md). |
| **WIP = 1** | Tại một thời điểm chỉ một story `in_progress`. Việc chen ngang phải đưa story hiện tại sang `blocked` hoặc `deferred` trước. |
| **ADR** | Bản ghi quyết định kiến trúc hoặc hành vi. Khuôn: [templates/decision.md](templates/decision.md); các bản ở [decisions/](decisions/). ADR đã `accepted` không sửa nội dung; muốn đổi thì lập ADR mới. |
| **Độ trưởng thành (H0–H5)** | Mức tiến hoá của harness. Hiện ở H2 đến H5: SQLite bền, quan sát chủ động, tự kiểm, quy trình tự cải tiến. |
| **Closure** | Bảng nghiệm thu đóng phiên bắt buộc ở cuối mỗi yêu cầu (AGENTS.md §0). |

## 2. Tác nhân và điều phối

| Thuật ngữ | Nghĩa |
|---|---|
| **Tác nhân** | Thành phần có mục `class` trong `.agents/registry.yaml`. Có ba lớp: operator, cognitive, conductor. Từ "agent" chỉ dùng cho lớp cognitive (rule 07 §1). |
| **Operator** | Tác nhân là script Python tất định, 0 token, vào ra cố định, chạy lại được. Không gọi là agent. |
| **Cognitive (agent)** | Tác nhân là mô hình ngôn ngữ, có phí token, chạy một lượt, không có công cụ. Hiện có `article-processor`; các tác nhân khác ở trạng thái `draft`. |
| **Conductor** | Tác nhân điều phối: quyết định bước kế tiếp và chính sách đợt. Hiện thực bằng `ops_daemon` (`master-orchestrator`). |
| **Registry** | `.agents/registry.yaml`, nguồn chân lý về tác nhân tồn tại. Tác nhân không có mục trong registry thì không tồn tại về mặt vận hành. |
| **Luồng** | Nhóm đợt chạy độc lập: tự động (daemon), bài tồn (chạy tay, nạp DB), thử nghiệm (chạy tay, không nạp DB). Mỗi luồng tối đa một đợt đang chạy. |
| **Pipeline** | `.agents/pipeline.yaml`, khai báo luồng điều phối: stage, tác nhân phụ trách, cổng. |
| **Skill** | Gói tri thức `SKILL.md` của một tác nhân. Tác nhân lúc chạy không nạp skill động; skill là phần nội dung đã nhúng vào persona. |
| **Mandate** | Uỷ quyền vận hành có hạn do người cấp (`/level L1`), lưu ở `agy_standing_order.yaml`. Tự gia hạn khi hệ thống khoẻ. Tên cũ: *standing order*. |
| **Cấp tự chủ** | L0 chỉ đo và báo. L1 tự mở đợt và chạy trọn tới nạp DB. Hai cấp L2, L3 trước đây đã gỡ. |
| **Breaker** | Bộ ngắt mạch theo provider: chặn gọi provider sau chuỗi lỗi đăng nhập, hạn mức, mạng, treo hoặc trả rỗng. |
| **Sentinel** | `ops-sentinel`: agent chẩn đoán sự cố, chỉ đề xuất một lệnh trong danh sách trắng. Người bấm thì daemon mới thi hành. |
| **Provider** | Nơi chạy mô hình: `agy` (mặc định), `openrouter`. |
| **Hold (giữ)** | Cờ do người đặt để tạm dừng riêng một tác nhân. *Kế hoạch, chưa có.* |
| **Zero-Tool** | Bất biến của agent: không gọi công cụ nào. Lượt gọi công cụ bị hook từ chối được đếm là vi phạm. |

## 3. Đợt và dữ liệu xử lý

| Thuật ngữ | Nghĩa |
|---|---|
| **Article Lane** | Đường xử lý duy nhất từ bài báo tới bản ghi phân tích (ADR 0010). Một agent xử lý trọn một bài trong một lượt. |
| **Đợt** | Một lần chạy Article Lane trên tối đa 100 bài. Mã `W` cộng tháng, ngày, giờ, phút lúc mở (`W10011434` là 01/10 lúc 14:34). Trong mã nguồn là `wave`. |
| **Lô** | Phần của một đợt gửi cho agy trong một tiến trình, tối đa 50 bài (`--batch`). Trong mã nguồn là `batch`. |
| **Packet** | Tệp `.task.json` của một lô, mang `i` (chỉ số), `t` (tiêu đề), `p` (các đoạn văn sạch). |
| **Bản đồ lô** | Tệp `.map.json` đi cùng packet: ánh xạ chỉ số cục bộ sang mã bài, kèm tầng ưu tiên và lý do. Ở lại trên máy, không gửi cho mô hình. |
| **Bản ghi gọn** | Kết quả mô hình trả về cho một bài: thực thể, tóm tắt, luận điểm, hàm ý, sắc thái, chỉ số đoạn chứng cứ. |
| **Bung bản ghi** | Bước `article_expand` biến bản ghi gọn thành hai lược đồ đầy đủ. Dựng trích dẫn nguyên văn từ chỉ số đoạn, 0 token. |
| **Vá (repair)** | Đóng gói lại đúng những bài chưa có bản ghi thành lô `_rNN` và chạy lại. Tối đa hai vòng mỗi đợt. |
| **Giữ chỗ** | Bài thuộc đợt chưa xong (đang chạy, PARKED, FAILED) không được đóng gói vào đợt khác. Nhả khi đợt DONE hoặc CANCELLED. |
| **Bài chờ** | Bài trong phạm vi tự động chưa có bản ghi phân tích đạt cổng DoD. Bản code-first không tính là đã phân tích. |
| **Tồn đọng** | Bài chờ nằm ngoài phạm vi tự động (`lookback_days`). Xử lý bằng việc riêng của người vận hành. |
| **Cổng DoD** | Kiểm định một bản ghi trước khi nạp DB: lược đồ, trích dẫn có căn cứ trong bài gốc, không chép nguyên văn vào luận điểm. |
| **Độ phủ** | Tỷ lệ bài của đợt có bản ghi đạt ở mỗi lớp (nhận diện thực thể, phân tích nội dung). Ngưỡng nạp là 90%. |
| **Hậu kiểm** | Bước `verify_wave` đối chiếu tập bài của đợt với DB sau khi nạp. |
| **Luật kích hoạt (T1, T2, T3)** | Ba điều kiện để sensor mở đợt: T1 đủ khối lượng (từ 100 bài chờ), T2 bài chờ lâu nhất quá 90 phút (trong giờ 06:00 đến 22:00), T3 đang trong khung giờ chốt phiên. |
| **PARKED** | Trạng thái đợt tạm dừng chờ điều kiện (breaker mở, độ phủ chưa đủ). Bài vẫn được giữ chỗ. |

## 4. Giám sát

| Thuật ngữ | Nghĩa |
|---|---|
| **Phòng điều khiển** | Trang web cục bộ `http://127.0.0.1:8787` do daemon phục vụ, gồm các màn Toàn cảnh, Đợt, Tác nhân, Sự cố, Cải tiến. |
| **Bảng điều khiển chữ** | Giao diện terminal `scripts/ops_console.py` (phím `Ctrl+Alt+O`). Khác Phòng điều khiển. |
| **Vết (span)** | Bản ghi một việc đã chạy trong đợt, lưu ở bảng `ops_spans`: tác nhân, thời gian, kết quả, token. Khác *trace (harness)* ở mục 1. |
| **Cây vết** | Toàn bộ vết của một đợt, xếp theo quan hệ cha con: workflow, bước, script, lô agy, cổng. |
| **Bản đồ tác nhân** | Sơ đồ các tác nhân trong registry với trạng thái hiện tại theo vết. |
| **Nhịp tim** | Mốc thời gian daemon ghi mỗi phút; quá 3 phút không ghi thì daemon bị coi là im lặng. |
| **Bản tin giám sát** | Tin Telegram lúc 08:00 và 18:00: mandate, đợt trong ngày, từng tác nhân, điểm khác thường. |
| **Đề xuất cải tiến** | Gợi ý do operator `improvement-proposer` sinh từ vết và KPI, kèm bằng chứng. Không bao giờ tự thi hành. |
| **Hộp thư cải tiến** | Danh sách đề xuất chờ người chọn Mở story, Hoãn hoặc Bác. |
| **SLI, SLO** | Chỉ số mức dịch vụ và mục tiêu của nó. *Kế hoạch, chưa có.* |
| **Bộ vàng** | Tập 40 đến 50 bài do người gắn nhãn đạt hoặc không đạt, dùng kiểm hồi quy trước khi đổi prompt hay model. *Kế hoạch, chưa có.* |

## 5. Sản phẩm dữ liệu

| Thuật ngữ | Nghĩa |
|---|---|
| **Bronze** | HTML thô đã cào, bất biến, đúng từng byte. `content_sha256` là bằng chứng không đổi. |
| **Silver** | Nền sạch, dựng lại được thuần từ Bronze (`project/data/silver/*`). Phân tích lại không cần cào lại. |
| **L1** | Lớp nhận diện thực thể từ tiêu đề, lưu ở bảng `l1_outputs`. |
| **Gold** | Lớp phân tích nội dung (tóm tắt, luận điểm, hàm ý, trích dẫn), lưu ở bảng `agent_outputs`. Do Article Lane tạo. |
| **Dedup** | Phát hiện bài trùng hai tầng: SHA-256 của URL và tiêu đề, cộng so khớp mờ. Bảng `seen_articles`. |
| **Nguồn tin** | Một trang tin (cafef.vn, vietstock.vn, ...), cấu hình ở `project/config/domains/*.yaml`. |
| **Từ điển sắc thái** | Danh sách từ sắc thái tiếng Việt theo luật; bài tiếng Anh mặc định trung tính. |
| **Hợp đồng bàn giao** | Ranh giới JSON giữa bên sản xuất và agent (`project/docs/design/08`, `09`). |

## 6. Một khái niệm, một tên

| Không dùng | Dùng | Ghi chú |
|---|---|---|
| standing order | mandate | Tên tệp `agy_standing_order.yaml` và lịch sử ADR 0011, 0012 giữ nguyên |
| Control Room, ops console (web) | Phòng điều khiển | Trong mã nguồn gói `control_room` |
| ops console (terminal) | bảng điều khiển chữ | Tên tệp `ops_console.py` giữ nguyên |
| agent (cho operator hoặc conductor) | tác nhân | Rule 07 §1 |
| wave | đợt | Chỉ giữ `wave` trong tên biến, tên tệp và tham số dòng lệnh |
| batch, mini-batch | lô | Chỉ giữ `batch` trong mã nguồn và `--batch` |
| trace (của ops_spans) | vết, cây vết | `trace` chỉ còn nghĩa bản ghi phiên của harness |
| hàng chờ, backlog | bài chờ, tồn đọng | Phân biệt theo phạm vi tự động |
| L2, L3 | không còn | Hai cấp này đã gỡ (ADR 0014) |
