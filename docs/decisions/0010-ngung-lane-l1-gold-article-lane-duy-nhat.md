# ADR 0010 — Ngừng lane L1/Gold hai tầng, Article Lane là đường xử lý duy nhất

- **Ngày:** 2026-09-23
- **Trạng thái:** **accepted**. Người dùng duyệt ngày 2026-09-23 với ba chỉ thị: gỡ row `agent_l1`/`agent_gold`, sửa `AGENTS.md` theo thiết kế lane mới, và xử lý triệt để nhiễu của lane cũ.
- **Lane:** **high-risk**, vì chạm `AGENTS.md`, registry và pipeline (Harness Core)
- **Story:** US-026 (dọn preset, job, tệp tồn, bộ chọn bài) · US-027 (`AGENTS.md`, registry, pipeline)
- **Thay thế một phần:** ADR 0005 (Subscriber-gated Gold export, L1 missed-only review, pruning 2.200 ký tự, mini-batch 5–10 task) và ADR 0008 (trần token). ADR 0003 (code-first L1) chỉ còn giá trị lịch sử.
- **Thiết kế lane mới:** `plans/20260918-1651-article-lane-unified/plan.md`

---

## 1. Bối cảnh

Article Lane chạy từ 18/09: một agent (`article-processor`, công cụ `agent_article`) xử lý trọn một bài, gồm nhận diện thực thể và phân tích nội dung, trong một bước cho cả lô. Lane cũ được giữ để quay lui với điều kiện "sau một chu kỳ vận hành sạch mới dọn". Đợt W365 ngày 21/09 (365 bài, 5 user nhận hàng) là chu kỳ đó.

Rà soát ngày 23/09 cho thấy lane cũ không nằm yên mà đang gây hại:

| Tàn dư lane cũ | Tác hại đo được |
|---|---|
| Radar vẫn khuyến nghị `l1_entity_matcher`, `requeue`, `l1_route` | Phiên điều phối tuân thủ luật Radar-first bị dẫn sang lane đã chết |
| Job `morninger` chạy `l1_route` + `l1_ingest --code-first` mỗi 15 phút | Ghi bản tra bảng vào `l1_outputs`. Bộ chọn bài của Article Lane coi bản ấy là đã phân tích, nên **2.915 bài ngày 10–17/09** không bao giờ được phân tích nội dung |
| `L1Runner` đòi dòng `l1_tasks` của lane cũ | 4 bài W365 bị loại với lý do `no l1_task` dù mô hình trả đúng |
| Tệp tồn trong thư mục đầu ra dùng chung, `--finish` quét cả thư mục | 85 tệp L1 cũ trượt schema bị nạp lại mỗi đợt, dòng `failed` bị thổi lên 123 |
| Row `agent_l1`/`agent_gold` trong preset | Chưa từng spawn được (ADR 0009 amendment), nhưng vẫn hiện trong danh sách công cụ của phiên điều phối |

## 2. Quyết định

1. **Article Lane là đường xử lý duy nhất.** Không còn đường quay lui sang L1/Gold hai tầng. Skill `l1-entity-matcher` được giữ vì nó là kiến thức nhận diện của `article-processor`. Skill `gold-financial-analyst` chỉ còn là tài liệu tham khảo.
2. **Gỡ khỏi vận hành:** row `agent_l1`/`agent_gold` trong preset; job `l1_route` của `morninger`; stage `l1_route`, `l1_match`, `gold_export`, `gold_analyze` trong pipeline (stage `l1_ingest`/`gold_ingest` gộp vào `article_expand`); agent `l1-router`, `gold-exporter`, `l1-entity-matcher`, `gold-financial-analyst` trong registry (chuyển `status: retired`).
3. **Giữ và đổi vai:** `l1_ingest.py` và `agent_ingest.py` ở lại làm cổng nghiệm thu DoD, nhưng chỉ được `article_run.py --finish` gọi, và chỉ với tệp của đúng đợt.
4. **Bản code-first không phải là phân tích.** Mọi phép đếm "đã phân tích" và bộ chọn bài bỏ qua `l1_source = 'code_first'`.
5. **Token là số ghi nhận, không phải cổng.** Không có trần hay mức cảnh báo token theo bài, theo lô hay theo đợt. Sổ cái ghi để người dùng tự đánh giá. Phần trần token của ADR 0008 hết hiệu lực.
6. **Cổng thật của một đợt** là cổng kỹ thuật: DB ghi được (kiểm trước khi tiêu token), nạp không lỗi, và độ phủ của đợt ≥ 90% ở cả hai lớp.

## 3. Hệ quả

- Tệp tồn chuyển (không xoá) sang `project/data/archive/legacy-lane-20260923/`, kèm `MANIFEST.json` để hoàn tác.
- Các dòng `l1_tasks` cũ trong DB được giữ làm lịch sử. Không script vận hành nào đọc bảng này.
- 2.915 bài bị kẹt quay lại hàng chờ của Article Lane. Việc chạy chúng là quyết định vận hành, không tự động.
- Tiến trình `morninger` đang chạy phải khởi động lại thì job `l1_route` mới dừng.

## 4. Quay lui

Nếu Article Lane trượt nghiệm thu hai đợt liên tiếp: khôi phục tệp từ `MANIFEST.json`, khôi phục row preset và job `morninger` từ git (commit trước ADR này), rồi lập ADR mới. Không có đường quay lui "tạm" nào nằm sẵn trong mã.
