---
name: story-dedup-clusterer
description: Xác nhận và gộp cụm các bài báo trùng một sự kiện tài chính từ nhiều nguồn, chọn bài canonical và gom danh sách nguồn.
---

# Story Dedup & Clustering Skill

> **Mục đích:** Xác nhận cụm bài trùng sự kiện đa nguồn do Operator tiền nhóm bằng SimHash, chọn một bài canonical cho mỗi cụm và gom danh sách nguồn để tầng Gold chỉ phân tích một lần.

## 1. Đầu vào

Đọc file task tại `data/agent_tasks/dedup/*.task.json`. Mỗi task chứa mảng `cluster_candidates[]`. Mỗi phần tử gồm các trường:

- `article_id`: định danh bài.
- `title`: tiêu đề nguyên văn.
- `source`: nguồn phát hành (`cafef`, `fireant`, `tnck`...).
- `simhash`: giá trị SimHash do Operator tính sẵn.
- `published_at`: thời điểm xuất bản (ISO 8601).
- `l1_entities`: mảng mã CP/chủ đề đã bóc sẵn (ví dụ `TICKER:HPG`).

Operator đã tiền nhóm ứng viên bằng độ gần SimHash. Nhiệm vụ của agent là XÁC NHẬN cụm, không phải tự tìm ứng viên.

## 2. Nhiệm vụ

Quyết định các bài nào cùng MỘT sự kiện thực tế (gộp) và các bài nào thuộc sự kiện khác (tách). Với mỗi cụm đã xác nhận:

- Chọn `canonical_article_id`: bài có `published_at` sớm nhất và tiêu đề đầy đủ nhất trong cụm.
- Gom `member_article_ids`: toàn bộ bài thuộc cụm, kể cả bài canonical.
- Gom `sources`: tập nguồn phân biệt của các thành viên.

## 3. Ràng buộc gộp (DoD dod-gatekeeper#dedup)

- Các bài trong một cụm BẮT BUỘC chia sẻ tối thiểu một `l1_entity` chung. Ghi tập chung vào `shared_entities`.
- Trường `rationale` phải trích dẫn chuỗi con NGUYÊN VĂN (exact substring) lấy từ các `title` liên quan, không diễn giải lại.
- Không gộp hai bài chỉ vì SimHash gần nhau khi tập thực thể của chúng khác nhau. Thực thể quyết định, SimHash chỉ là gợi ý ứng viên.
- Bài không đạt ràng buộc trên đứng riêng thành cụm một thành viên với chính nó làm canonical.

## 4. Output

Ghi kết quả tại `data/agent_outputs_dedup/*.output.json`. Nội dung là MẢNG JSON các object theo cấu trúc:

```json
{
  "cluster_id": "<id>",
  "canonical_article_id": "<id>",
  "member_article_ids": ["..."],
  "sources": ["cafef", "fireant"],
  "shared_entities": ["TICKER:HPG"],
  "confidence": 0.9,
  "rationale": "<trích dẫn nguyên văn từ titles>"
}
```

Gán `confidence` trong khoảng [0, 1] phản ánh độ chắc chắn của quyết định gộp.

## 5. Chế độ 2-I/O (Strict Anti-Token-Burn)

- Đọc file task bằng `view_file` DUY NHẤT một lần cho mỗi task.
- Ghi kết quả bằng `write_to_file` DUY NHẤT một lần với `Overwrite: true`.
- CẤM gọi discovery tools (`grep`, `find`, `list_dir`). Task đã cung cấp đủ dữ liệu.
- Gom lô 15 bài mỗi đợt. Chạy tối đa 2 luồng song song có kiểm soát để chống lỗi 429 (rate limit).

## 6. Giá trị

Nhờ gộp cụm, tầng Gold chỉ phân tích bài canonical một lần rồi gán kết quả cho N nguồn thành viên. Cách này cắt phần token trùng lặp và được đo bằng KPI `gold_dedup_savings_pct`.

## 7. Khai báo hệ thống

- Agent khai báo tại `.agents/registry.yaml` với `id: story-dedup-clusterer`, `status: draft`.
- Agent chạy ở stage `story_dedup` (optional) trong `.agents/pipeline.yaml`.
- Nạp kết quả từ `data/agent_outputs_dedup/*.output.json` về hệ thống qua operator ingest tương ứng.
