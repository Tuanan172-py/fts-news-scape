---
name: adversarial-dod-verifier
description: Kiểm định ngữ nghĩa đối kháng output Gold, phát hiện implication rỗng, hallucination, sentiment sai và key_points sao chép mà cổng DoD tất định bỏ sót.
---

# Adversarial DoD Verifier Skill

> **Mục đích:** Đóng vai QA ngữ nghĩa đối kháng cho tầng Gold News-Scape, kiểm phần suy luận mà cổng DoD tất định không kiểm được.

## 1. Phạm vi và tư thế

Cổng DoD tất định (operator) đã kiểm schema và exact-substring citations. Skill này kiểm chất lượng suy luận: implication, hallucination, sentiment, sao chép, tính abstractive. Giữ tư thế HOÀI NGHI: mặc định gắn cờ defect khi nghi ngờ, không suy diễn có lợi cho output.

## 2. Đầu vào

Đọc một mẫu (sample) các cặp:

- Output Gold: `data/agent_outputs/*.output.json`, gồm 7 trường v2-lean: `article_id`, `summary`, `key_points`, `implication`, `sentiment`, `time_sensitivity`, `citations`.
- Task gốc: `data/agent_tasks/*.task.json`, chứa `cleaned_text` làm nguồn chân lý.

Ghép cặp theo `article_id`. Đọc bằng `view_file`. CẤM discovery tools.

## 3. Năm phép kiểm đối kháng

Áp dụng cho từng bài trong mẫu.

### 3.1 (a) implication đặc hiệu

Yêu cầu `implication` chỉ rõ thực thể hưởng lợi hoặc chịu rủi ro và tác động cụ thể (doanh thu, dòng tiền, định giá, thị giá), độ dài >=40 ký tự. Gắn defect `vague_implication` nếu chung chung, ví dụ "phản ánh thông tin quan trọng".

### 3.2 (b) không hallucination

Truy mọi số liệu, mã cổ phiếu, tên tổ chức xuất hiện trong `summary`, `key_points`, `implication` về `cleaned_text`. Gắn defect `hallucination` nếu output bịa dữ kiện không tồn tại trong nguồn.

### 3.3 (c) sentiment đúng

Đối chiếu `sentiment` (positive/negative/neutral) với nội dung bài. Gắn defect `sentiment_mismatch` nếu lệch, ví dụ tin thua lỗ mà gắn positive.

### 3.4 (d) key_points không sao chép

Đối chiếu từng phần tử `key_points` với các chuỗi `citations` (Value-Added Invariant rule 05). Gắn defect `keypoint_copy` nếu trùng nguyên văn.

### 3.5 (e) summary abstractive

Yêu cầu `summary` diễn giải lại nội dung, không cắt dán câu thô. Gắn defect `extractive_summary` nếu chỉ sao chép câu từ `cleaned_text`.

## 4. Output báo cáo

Ghi `data/qa/dod_semantic_report.json` bằng `write_to_file` một lần. Cấu trúc là MẢNG JSON, mỗi phần tử một bài:

```json
{
  "article_id": "<id>",
  "verdict": "pass" | "defect",
  "defects": [
    { "type": "vague_implication", "evidence": "<trich>", "severity": "low|med|high" }
  ],
  "sample_ok": true
}
```

Đặt `verdict` là `defect` khi có ít nhất một defect, ngược lại `pass`. Trường `evidence` là chuỗi trích từ output hoặc `cleaned_text`. Các giá trị `type` hợp lệ: `vague_implication`, `hallucination`, `sentiment_mismatch`, `keypoint_copy`, `extractive_summary`.

## 5. Nạp harness backlog

Đề xuất nạp mỗi defect severity `high` vào harness backlog để nuôi vòng tự cải tiến. Nêu lệnh gợi ý trong báo cáo:

```
python scripts/harness_cli.py backlog add --title <tiêu đề> --pain <mô tả> --component gold_quality
```

## 6. Chế độ vận hành

- Chế độ 2-I/O: đọc mẫu bằng `view_file`, ghi báo cáo bằng `write_to_file` một lần.
- Gom lô 8 bài mỗi đợt, chạy 1 luồng.
- CẤM discovery tools.

## 7. DoD: dod-gatekeeper#verifier

- Mỗi `verdict` phải kèm bằng chứng: `evidence` là chuỗi trích từ output hoặc `cleaned_text`.
- Mọi bài trong mẫu phải có kết luận rõ ràng (`pass` hoặc `defect`).
- Đặt `sample_ok` là `false` nếu thiếu cặp task-output hoặc dữ liệu vào lỗi.

## 8. Khai báo hệ thống

Đăng ký tại `.agents/registry.yaml`:

```yaml
- id: adversarial-dod-verifier
  status: draft
```

Khai báo stage `gold_qa` (optional, chạy sau `gold_ingest`) trong `.agents/pipeline.yaml`:

```yaml
- stage: gold_qa
  agent: adversarial-dod-verifier
  optional: true
  after: gold_ingest
```

KPI theo dõi: `semantic_defect_catch_rate`.
