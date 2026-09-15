---
name: entity-curator
description: Đề xuất bổ sung catalog thực thể từ unlisted_candidates kèm bằng chứng nguyên văn, ghi file delta riêng và chờ Human duyệt trước khi nạp.
---

# Entity Curator Skill

> **Mục đích:** Chuyển các ứng viên thực thể tần suất cao (chưa có trong catalog) thành entry catalog chuẩn hóa, kèm bằng chứng, để Human duyệt qua ADR trước khi nạp vào từ điển gốc.

---

## 1. Cảnh Báo Quyền Hạn (TIER 3 HIGH-RISK)

Agent này thuộc TIER 3 HIGH-RISK vì chạm Data Contract của catalog thực thể.

1. Chỉ ĐƯỢC PHÉP ghi một file đề xuất duy nhất: `data/proposals/entity_catalog_delta.json`.
2. TUYỆT ĐỐI KHÔNG ghi trực tiếp vào `project/data/entities/entities.json` hoặc `project/data/entities/entities.xlsx`.
3. Kết quả chỉ được nạp vào catalog sau khi có ADR được Human duyệt (activation_gate).
4. Mọi entry đề xuất mang `human_decision: "pending"`; agent không tự quyết định chấp nhận.

---

## 2. Đầu Vào (Inputs)

1. Nhận danh sách `unlisted_candidates` đã gom theo tần suất, do operator trích từ `l1_outputs` trong `data/monocle.db`.
2. Mỗi ứng viên có cấu trúc:
   - `surface`: chuỗi bề mặt xuất hiện trong tin.
   - `frequency`: số lần xuất hiện đã gom.
   - `sample_titles[]`: các tiêu đề tin chứa surface.
   - `sample_article_ids[]`: các mã bài tương ứng.

---

## 3. Nhiệm Vụ (Proposal Task)

Với mỗi ứng viên tần suất cao, đề xuất một entry catalog gồm các trường:

1. `proposed_entity_id`: dùng đúng tiền tố chuẩn — `TICKER:`, `ETF:`, `INDEX:`, `EXCHANGE:`, `IND_GICS1/2/3:`, `MACRO_GEO:`, `MACRO_THEME:`, `ASSET_CLASS:`, `INSTITUTION:`.
2. `type`: thuộc 12 Enum — `TICKER`, `ETF`, `SECURITY_OTHER`, `INDEX`, `EXCHANGE`, `INDUSTRY_GICS1`, `INDUSTRY_GICS2`, `INDUSTRY_GICS3`, `MACRO_GEO`, `MACRO_THEME`, `ASSET_CLASS`, `INSTITUTION`.
3. `canonical_name`: tên chuẩn hóa in hoa không dấu.
4. `aliases[]`: các biến thể bề mặt gom về entry này.
5. `target_sheet`: một trong `Securities`, `Industries`, `Indices`, `Exchanges`, `Nations`, `Themes`, `Assets`, `Institutions` — ánh xạ theo entity-system-invariants.

---

## 4. Bộ Lọc Chống Nhiễu (Morphological Guard — BẮT BUỘC)

Đồng bộ với morphological guard trong entity-system-invariants. KHÔNG đề xuất:

1. Địa danh Việt Nam (ví dụ: Mỹ Tho, Mỹ Thuận, Mỹ Đình).
2. Tên người kèm danh xưng (Bà, Ông, Thị, Văn).
3. Thương hiệu địa phương nhỏ, không có ý nghĩa định tuyến tài chính.
4. Từ viết tắt phổ biến không phải thực thể (GDP, CPI, CEO).

Chỉ đề xuất thực thể tài chính thực, có ý nghĩa định tuyến trong hệ News-Scape.

---

## 5. Output (entity_catalog_delta.json)

Ghi `data/proposals/entity_catalog_delta.json` là MẢNG JSON. Mỗi phần tử:

```json
{
  "surface": "...",
  "proposed_entity_id": "TICKER:XYZ",
  "type": "TICKER",
  "canonical_name": "...",
  "aliases": ["..."],
  "target_sheet": "Securities",
  "frequency": 12,
  "evidence_article_ids": ["..."],
  "evidence_titles": ["<trich nguyen van>"],
  "confidence": 0.8,
  "human_decision": "pending"
}
```

---

## 6. Chế Độ I/O Tiết Chế (Constrained I/O)

1. Đọc dữ liệu ứng viên bằng `view_file`.
2. Ghi đề xuất bằng `write_to_file`, một lần cho mỗi lô.
3. Gom lô 10 ứng viên mỗi đợt, chạy 1 luồng (concurrency = 1) để giữ mức thận trọng.

---

## 7. Definition of Done (dod-gatekeeper#curator)

1. Mỗi đề xuất có `evidence_titles` là chuỗi con nguyên văn trích từ tin thật (không diễn giải lại).
2. `type` thuộc đúng 12 Enum liệt kê tại mục 3.
3. `proposed_entity_id` mang đúng tiền tố tương ứng với `type`.
4. Không đề xuất trùng `entity_id` đã tồn tại trong catalog gốc.

---

## 8. Khai Báo Registry & Ranh Giới Skill

1. Khai báo tại `.agents/registry.yaml`:
   - `id: entity-curator`
   - `status: draft`
   - `tier: high-risk`
   - `activation_gate: ADR` (chờ Human duyệt trước khi nạp catalog).
2. Skill xếp ở stage `catalog-growth`, nằm NGOÀI đường giao hàng chính (delivery path).
3. Ranh giới với skill khác:
   - `watchlist-curator` phụ trách phần vận hành Watchlist người dùng.
   - `entity-curator` chỉ đề xuất bổ sung catalog thực thể gốc; không quản trị Watchlist.
