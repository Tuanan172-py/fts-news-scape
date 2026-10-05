# ADR 0016 — Cụm hoá trùng lặp, kế thừa kết quả và tín hiệu insight

- **Loại tài liệu:** giải thích (explanation), ghi lại một quyết định.
- **Ngày:** 2026-10-02
- **Trạng thái:** accepted
- **Lane:** high-risk
- **Story:** US-033
- **Kế thừa:** ADR 0010, ADR 0012 và ADR 0013. ADR này sửa bất biến "mọi bài đều được xử lý đầy đủ" của ADR 0010.
- **Người duyệt:** người dùng duyệt ngày 2026-10-02 bằng câu "đồng ý triển khai trọn vẹn" cho `docs/proposals/dedup-architecture-2026-10-01.md` và `docs/proposals/insight-analytics-2026-10-01.md`.

> ADR đã `accepted` không sửa nội dung. Muốn đổi thì lập ADR mới và ghi "thay thế một phần bởi ADR NNNN" ở dòng Trạng thái của ADR cũ.

## 1. Bối cảnh

Một sự kiện được nhiều tờ báo đăng lại, và Article Lane đang gọi mô hình cho từng bản. Số đo ngày 2026-10-01 trên DB vận hành:

- Trong 3 ngày có 1.314 bài, trong đó 9 bài chép gần nguyên văn và 33 bài cùng sự kiện với một bài khác.
- Tám cặp bài có tiêu đề khác nhau nhưng nội dung giống hệt, vì cùng một mã bài bị đổi tiêu đề và slug.
- Tần suất và độ rộng đưa tin của một chủ đề là tín hiệu đầu tư, nên không được xoá bài trùng.
- Khi tăng số nguồn, tỷ lệ trùng sẽ tăng và token bị tiêu cho những bài không thêm thông tin.

Hard Gate: thêm bảng DB, đổi bất biến Article Lane và thêm giá trị `l1_source`.

## 2. Quyết định

### 2.1. Sổ phát hiện

Bảng `discovered_urls` ghi mọi URL thấy được trước mọi bước lọc. Biến thể URL của một bài nằm ở `url_aliases`. Trạng thái cuối chỉ có `captured`, `gone` và `dead_letter`.

### 2.2. Cụm câu chuyện

Bảng `story_clusters` và `cluster_members` ghi vai trò từng bài: `canonical`, `copy` hoặc `candidate`. Việc cụm hoá không xoá và không sửa `articles`.

### 2.3. Điều kiện chép lại

Một bài chỉ được gán `copy` khi nội dung trùng khớp tuyệt đối, hoặc containment shingle từ 0,95 trở lên. Hai tập số liệu đầu bài và hai tập mã CP phải trùng nhau. Bài quá ngắn không được so bằng shingle.

### 2.4. Kế thừa kết quả

Bài `copy` không vào packet. Script `apply_inheritance` ghi một dòng `l1_outputs` và `agent_outputs` với `l1_source = 'inherited'`, trỏ về bài gốc bằng `inherited_from`. Giá trị `inherited` được tính là đã phân tích. Giá trị `code_first` vẫn bị loại.

### 2.5. Giữ bài chép chờ bài gốc

Bộ chọn bài giữ bài `copy` tối đa 48 giờ kể từ lúc cụm hoá. Hết hạn mà bài gốc chưa có kết quả thì bài chép được trả về bộ chọn bài.

### 2.6. Bất biến sửa đổi

Bất biến "mọi bài đều được xử lý đầy đủ" đọc thành hai vế. Mọi câu chuyện được phân tích đầy đủ một lần. Mọi bài có kết quả và vai trò trong cụm. Ngưỡng độ phủ 90% giữ nguyên, và tử số gồm cả bài kế thừa.

### 2.7. Bảng tín hiệu phái sinh

`signal_daily`, `entity_links` và `source_profile` dựng lại hoàn toàn từ `articles`, `l1_outputs`, `agent_outputs` và `cluster_members`. Script `signal_build.py` chạy 0 token, xoá và dựng lại được.

### 2.8. Phần chưa làm

Ba mục dưới đây chưa triển khai, và mỗi mục cần một quyết định riêng:

- Chế độ chênh cho bài `candidate` (P3). Mục này đổi hợp đồng đầu ra của mô hình. Chỉ một đợt chạy mô hình thật có người duyệt mẫu mới kiểm chứng được.
- Đối chiếu với giá (I3). Mục này cần nguồn dữ liệu giá và xác minh điều khoản sử dụng.
- Cờ `is_promotional` (I5). Mục này đổi hợp đồng mô hình.

## 3. Phương án đã loại

| Phương án | Lý do loại |
|---|---|
| Xoá hoặc ẩn bài `copy` khỏi `articles` | Trái ADR 0013 và làm mất tín hiệu tần suất. |
| Để LLM quyết định bản sao kỹ thuật | Việc này có đáp án tất định, nên chỉ tốn token và thêm biến thiên. |
| Gộp bắc cầu mọi cạnh cùng mã CP | Thử trên dữ liệu thật gộp 10 sự kiện khác nhau của PNJ thành một cụm. |
| Cho bản viết lại 0,8 kế thừa kết quả | Trích dẫn nguyên văn của bài gốc sẽ không còn nằm trong bài chép. |
| Vector DB và embedding | Chỉ mục shingle đủ cho 2.000 đến 5.000 bài mỗi ngày. |

## 4. Hệ quả

**Được:**

- Bài chép nguyên văn không tốn token mà vẫn có kết quả đầy đủ.
- Tần suất, độ rộng và tốc độ lan truyền của một chủ đề tính được vì mọi bài còn nguyên.
- Cảm biến, radar và giao hàng không đổi cách đếm vì đã dùng điều kiện `l1_source <> 'code_first'`.

**Phải chấp nhận:**

- Bài gốc phân tích lỗi thì bài chép chờ tối đa 48 giờ. Hết hạn bài chép được phân tích riêng.
- Ngưỡng 0,95 làm lọt nhiều bản viết lại. Chúng vẫn được phân tích đầy đủ, nên chỉ mất khả năng tiết kiệm.
- Sổ phát hiện đổi khoá khi thêm mẫu mã bài của nguồn mới. Lệnh `capture_reconcile.py rekey` xử lý việc này.

## 5. Quay lui

Dừng bước cụm hoá bằng cách bỏ lời gọi `run_story_cluster` trong `morninger`, và dùng cờ `--no-cluster` của `article_pack`. Xoá các dòng `l1_outputs` và `agent_outputs` có `l1_source = 'inherited'` để bài chép quay về hàng đợi. Các bảng mới là bảng phái sinh, có thể xoá mà không ảnh hưởng `articles`. Người vận hành thực hiện.
