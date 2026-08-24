---
name: l1-entity-matcher
description: Nhận diện thực thể chứng khoán Việt Nam từ tiêu đề tin tức (mã CP, doanh nghiệp, chỉ số, sàn, ngành) theo chuẩn l1-entity-output-v1.
---

# L1 Entity Matcher Skill

> **Mục đích:** Hướng dẫn Subagent Flash nhận diện nhanh và chính xác 100% các thực thể trong tiêu đề bài viết.

## 1. Nguồn dữ liệu & Input
- **Đầu vào**: Các task packet trong `data/agent_tasks/l1/*.task.json`.
- **Trường cần phân tích**: `input.title` (kết hợp tra cứu `input.code_first` nếu có).
- **Từ điển thực thể**: `project/data/entities/entities.json` hoặc tra cứu theo ontology 10 danh mục.

## 2. Quy tắc Nhận diện (Matching Rules)
1. **Mã Cổ phiếu (Tickers)**:
   - Nhận diện các token in hoa 3 ký tự (ví dụ: `VHM`, `HPG`, `FPT`, `MWG`, `VCB`...).
   - Loại trừ tuyệt đối các từ viết tắt thông dụng trong tiếng Việt nằm trong stoplist (ví dụ: `TGD`, `HĐQT`, `UBCK`, `NĐT`, `TPHCM`, `USD`, `VND`...).
2. **Tên Doanh nghiệp & Alias**:
   - Khớp tên đầy đủ hoặc tên thương hiệu thông dụng (ví dụ: `Vinhomes` $\rightarrow$ `VHM`, `Thế Giới Di Động` $\rightarrow$ `MWG`, `Hòa Phát` $\rightarrow$ `HPG`).
3. **Chỉ số & Sàn**:
   - Khớp `VN-Index`, `VNINDEX`, `VN30`, `HNX`, `UPCoM`, `HoSE`.
4. **Ngành GICS**:
   - Khớp tên ngành cấp 1, 2, 3 (ví dụ: `Bất động sản`, `Ngân hàng`, `Thép`, `Bán lẻ`...).

## 3. Quy chuẩn Output JSON
Ghi vào `data/agent_outputs_l1/<article_id>.json`:
- `recognized`: `true` nếu tìm thấy $\ge 1$ thực thể, `false` nếu không có.
- `entities`: Mảng các thực thể với `surface` (chuỗi con nguyên văn của tiêu đề), `entity_id`, `type`, `confidence` ($\ge 0.85$).
- `categories`: Đánh dấu `done` cho các nhóm có thực thể, `none` cho nhóm trống.
- `citations`: Trích dẫn `source_span` là chuỗi con nguyên văn của tiêu đề.
- `processing_metadata`:
  ```json
  {
    "agent_provider": "antigravity",
    "model_used": "flash",
    "timestamp": "<ISO_NOW_VN>",
    "schema_version": "1.0"
  }
  ```
