---
name: l1-entity-matcher
description: Nhận diện thực thể tài chính đa tầng từ tiêu đề tin tức (mã CP, doanh nghiệp, chỉ số, sàn, ngành GICS 3 cấp, vĩ mô, quốc gia, loại tài sản, định chế) theo chuẩn l1-entity-output-v1.
---

# L1 Entity Matcher Skill

> **Mục đích:** Hướng dẫn Subagent Flash nhận diện nhanh và chính xác 100% các thực thể trong tiêu đề bài viết dựa trên Ontology 10 Miền và xuất JSON chuẩn Definition-of-Done (DoD).

## 1. Nguồn Dữ Liệu & Input Task
- **Task Packet**: `data/agent_tasks/l1/*.task.json`.
- **Trường cần phân tích**: `input.title` (kết hợp tra soát `input.code_first` nếu có).
- **Từ điển Master Catalog**: `project/data/entities/entities.json` và `project/data/entities/taxonomy.json`.

---

## 2. Quy Tắc Nhận Diện 10 Miền Thực Thể (Matching Rules)

1. **Mã Cổ phiếu & Chứng khoán (`TICKER`, `ETF`, `SECURITY_OTHER`)**:
   - Khớp mã in hoa 3 ký tự (ví dụ: `HPG`, `VHM`, `FPT`, `E1VFVN30`).
   - Loại trừ stoplist từ viết tắt phổ biến: `GDP`, `CPI`, `PMI`, `FED`, `USD`, `VND`, `CEO`, `HĐQT`, `UBCK`, `NĐT`, `TPHCM`...
2. **Tên Doanh nghiệp & Thương hiệu Alias (`TICKER`)**:
   - Khớp tên đầy đủ hoặc tên rút gọn/thương hiệu (ví dụ: `Vinhomes` $\rightarrow$ `TICKER:VHM`, `Thế Giới Di Động` $\rightarrow$ `TICKER:MWG`, `Hòa Phát` $\rightarrow$ `TICKER:HPG`, `Vietcombank` $\rightarrow$ `TICKER:VCB`).
3. **Chỉ số & Sàn giao dịch (`INDEX`, `EXCHANGE`)**:
   - `INDEX`: Khớp `VN-Index`, `VNINDEX`, `VN30`, `VNXALL`, `HNX-Index`, `UPCoM-Index`.
   - `EXCHANGE`: Khớp `HOSE`, `HNX`, `UPCoM`. *(Lưu ý: Chỉ ghi nhận sàn khi tiêu đề nói về diễn biến sàn, không chấm cho hậu tố "(HOSE)" trong tên hồ sơ doanh nghiệp)*.
4. **Ngành nghề GICS 3 Cấp (`INDUSTRY_GICS1/2/3`)**:
   - Khớp tên ngành cấp 1, 2, 3 (ví dụ: `Bất động sản`, `Ngân hàng`, `Thép`, `Dầu khí`, `Dược phẩm`, `Bán lẻ`, `Quỹ đầu tư`...).
5. **Quốc gia & Địa chính trị (`MACRO_GEO`)**:
   - Khớp tên quốc gia/khu vực: `Mỹ` / `Hoa Kỳ` / `US` (`MACRO_GEO:MY`), `Trung Quốc` / `Bắc Kinh` (`MACRO_GEO:TRUNG_QUOC`), `Châu Âu` / `EU` / `Eurozone` (`MACRO_GEO:EU`), `Nhật Bản` (`MACRO_GEO:NHAT_BAN`), `Nga` (`MACRO_GEO:NGA`), `Hàn Quốc` (`MACRO_GEO:HAN_QUOC`), `Đông Nam Á` / `ASEAN` (`MACRO_GEO:DONG_NAM_A`), `Ấn Độ` (`MACRO_GEO:AN_DO`).
6. **Chủ đề Vĩ mô (`MACRO_THEME`)**:
   - Khớp các khái niệm vĩ mô cốt lõi: `lãi suất` / `lãi suất điều hành` (`MACRO_THEME:LAI_SUAT`), `tỷ giá` / `USD/VND` / `DXY` (`MACRO_THEME:TY_GIA`), `lạm phát` / `CPI` (`MACRO_THEME:LAM_PHAT`), `thuế quan` / `thuế chống bán phá giá` (`MACRO_THEME:THUE_THUONG_MAI`), `tăng trưởng GDP` (`MACRO_THEME:GDP_TANG_TRUONG`), `đầu tư công` / `sân bay Long Thành` / `cao tốc` (`MACRO_THEME:DAU_TU_CONG`), `FDI` / `vốn ngoại` (`MACRO_THEME:FDI`), `tín dụng` / `nợ xấu` / `room tín dụng` (`MACRO_THEME:TIN_DUNG`), `nâng hạng thị trường` / `FTSE` / `MSCI` (`MACRO_THEME:NANG_HANG_TTCK`).
7. **Loại Tài sản & Hàng hóa (`ASSET_CLASS`)**:
   - Khớp các lớp tài sản: `trái phiếu` / `TPDN` / `trái chủ` (`ASSET_CLASS:TRAI_PHIEU`), `cổ phiếu` / `TTCK` / `thanh khoản` (`ASSET_CLASS:CO_PHIEU`), `vàng` / `vàng SJC` / `vàng nhẫn` (`ASSET_CLASS:VANG`), `dầu thô` / `dầu Brent` / `giá dầu` / `OPEC` (`ASSET_CLASS:DAU_THO`), `nhà đất` / `bất động sản` / `đất nền` (`ASSET_CLASS:BAT_DONG_SAN_TAI_SAN`), `tiền mã hóa` / `crypto` / `Bitcoin` / `BTC` (`ASSET_CLASS:TIEN_MA_HOA`), `nông sản` / `giá gạo` / `cà phê` / `cao su` (`ASSET_CLASS:HANG_HOA_NONG_SAN`).
8. **Định chế & Cơ quan Quản lý (`INSTITUTION`)**:
   - Khớp cơ quan chính sách: `Ngân hàng Nhà nước` / `NHNN` / `SBV` / `OMO` (`INSTITUTION:NHNN`), `Ủy ban Chứng khoán` / `UBCKNN` / `SSC` / `KRX` (`INSTITUTION:UBCKNN`), `Bộ Tài chính` / `BTC` / `Tổng cục Thuế` (`INSTITUTION:BO_TAI_CHINH`), `Fed` / `Cục Dự trữ Liên bang` / `FOMC` (`INSTITUTION:FED`), `ECB` (`INSTITUTION:ECB`), `BOJ` (`INSTITUTION:BOJ`), `World Bank` / `IMF` (`INSTITUTION:WB_IMF`).

---

## 3. Nguyên Tắc Xử Lý Từ Ngắn & Chống False Positive
- **Từ ngắn được bảo vệ (`PROTECTED_SHORT_WORDS`)**: Các từ ngắn 2-3 ký tự như *"Mỹ", "Quỹ", "Fed", "Vàng", "Dầu", "CPI", "GDP", "SBV", "ECB", "BOJ", "OMO", "TPDN", "HRC", "BĐS"* là các thực thể hợp lệ, KHÔNG được bỏ qua.
- **Ranh giới từ (Word Boundary)**: Phải nhận diện theo ranh giới từ hoàn chỉnh, không bắt nhầm chuỗi con trong từ phức (ví dụ: *"quyết định"* $\neq$ *"Quỹ"*, *"mỹ thuật"* $\neq$ *"Mỹ"*, *"dầu ăn"* $\neq$ *"Dầu thô"*).
- **Quy tắc Tin Công bố thông tin (CBTT Positional Exemption)**:
  - Định dạng `MÃ: Nội dung` ở đầu tiêu đề (ví dụ: `VND: Báo cáo tình hình quản trị...`) luôn là mã chứng khoán chính thức, ngay cả khi mã đó nằm trong stoplist viết tắt tiền tệ (`VND`).
- **Phòng ngừa Nhầm lẫn Thuật ngữ Ngân hàng (Bank PGD Guard)**:
  - Cụm từ `PGD` trong thông báo của ngân hàng (hoặc đứng trước tên địa danh: *"PGD Chợ Tân Bình"*, *"PGD Quận 9"*, *"Chi nhánh/PGD"*) là **Phòng Giao Dịch**, TUYỆT ĐỐI KHÔNG gán cho mã chứng khoán `TICKER:PGD` (Khí thấp áp).
- **Hệ sinh thái & Thương hiệu Con (Ecosystem & Subsidiary Brands)**:
  - Khi tiêu đề nhắc đến các thương hiệu bán lẻ hoặc công ty con cốt lõi, Subagent phải ánh xạ về mã tập đoàn mẹ niêm yết:
    - `Bách Hóa Xanh`, `Điện Máy Xanh`, `An Khang` $\rightarrow$ `TICKER:MWG`
    - `WinCommerce`, `WinMart`, `Masan Consumer`, `Phúc Long` $\rightarrow$ `TICKER:MSN`
    - `FE Credit`, `VPBankS` $\rightarrow$ `TICKER:VPB`
    - `VinFast`, `Vinpearl`, `Xanh SM` $\rightarrow$ `TICKER:VIC`
    - `Becamex`, `Becamex Tokyu` $\rightarrow$ `TICKER:BCM`
- **Chống Nhầm lẫn Tên người với Quốc gia (Morphological Guard)**:
  - Từ `Nga` đứng sau danh xưng hoặc họ đệm (*"Bà Trần Kim Nga"*, *"Nga Rose"*) là tên người Việt/tên tài khoản, KHÔNG được gán nhãn `MACRO_GEO:NGA`.
  - Từ `Mỹ` đứng trước danh từ riêng tiếng Việt (*"Mỹ Thuận"*, *"Mỹ Tho"*, *"Mỹ Đình"*, *"Mỹ Thủy"*, *"Á Mỹ"*) là địa danh/thương hiệu, KHÔNG được gán nhãn `MACRO_GEO:MY`.

---

## 4. Quy Chuẩn Output JSON (`l1-entity-output-v1`)

Ghi kết quả vào `data/agent_outputs_l1/<article_id>.json`:

```json
{
  "l1_output_version": "1.0",
  "article_id": "<article_id>",
  "title": "<nguyên văn tiêu đề>",
  "recognized": true,
  "entities": [
    {
      "surface": "<chuỗi con nguyên văn trong title>",
      "entity_id": "<ID chuẩn, ví dụ: TICKER:VHM hoặc MACRO_THEME:LAI_SUAT>",
      "type": "TICKER",
      "method": "exact_code | alias | semantic",
      "in_list": true,
      "confidence": 0.95
    }
  ],
  "categories": {
    "ticker_company": "done | none | out_of_list",
    "etf_fund": "done | none | out_of_list",
    "index": "done | none | out_of_list",
    "exchange": "done | none | out_of_list",
    "industry_sector": "done | none | out_of_list",
    "macro_geo": "done | none | out_of_list",
    "asset_class": "done | none | out_of_list",
    "institution": "done | none | out_of_list"
  },
  "unlisted_candidates": [],
  "citations": [
    {
      "source_span": "<chuỗi con nguyên văn của title>"
    }
  ],
  "confidence": 0.95,
  "processing_metadata": {
    "agent_provider": "antigravity",
    "model_used": "flash",
    "timestamp": "<ISO_NOW_VN>",
    "schema_version": "1.0"
  }
}
```

---

## 5. Chế độ Gom Lô Siêu Tốc (Consolidated Batch Mode)

Packet L1 chỉ mang **tiêu đề**, không mang `cleaned_text`, nên gom lô được **25 bài/file** (Gold chỉ 5–10).

Khi nhận file task dạng gom lô `data/agent_tasks/l1/l1_batch_XX.task.json`:

1. **Một lần đọc duy nhất**: Gọi `view_file` đọc toàn bộ `l1_batch_XX.task.json`.
2. **Tra soát theo `code_first`**: Mỗi task trong `tasks[]` đã có sẵn kết quả khớp bằng code
   (`code_first.entity_ids`, `code_first.industries`, `code_first.relevance`). Nhiệm vụ là
   **XÁC NHẬN / SỬA / BỔ SUNG**, không nhận diện lại từ đầu:
   - `entity_ids` đúng → giữ, `method: "exact_code"` hoặc `"alias"`.
   - Code bắt nhầm (vd "quyết định" → `Quỹ`) → **BỎ**.
   - Code bỏ sót (đặc biệt tên thương hiệu, chủ đề vĩ mô, loại tài sản) → **THÊM**, `method: "semantic"`.
3. **Một lần ghi duy nhất**: Ghi kết quả cả lô vào
   `data/agent_outputs_l1/l1_batch_XX.output.json` dưới dạng **mảng JSON** các object
   `l1-entity-output-v1` (đúng schema ở §4):

```json
[
  { "l1_output_version": "1.0", "article_id": "<article_id_1>", "title": "...", "recognized": true, "entities": [], "categories": {}, "citations": [], "processing_metadata": {} },
  { "l1_output_version": "1.0", "article_id": "<article_id_2>", "...": "..." }
]
```

> 25 bài/lô ⇒ giảm ~96% số lần gọi công cụ I/O so với xử lý từng file lẻ.

### Bẫy làm hỏng DoD (đọc kỹ trước khi ghi)

- `entities[].surface` và `citations[].source_span` **BẮT BUỘC là chuỗi con NGUYÊN VĂN của
  `tasks[i].title`** — copy y nguyên, không sửa hoa/thường, không bỏ dấu, không rút gọn.
- `recognized: true` ⇒ phải có **≥1 entity VÀ ≥1 citation**. Không nhận ra gì thì
  `recognized: false`, `entities: []`, `citations: []`, mọi `categories` là `"none"`.
- `categories.<nhóm> = "done"` ⇒ phải có **≥1 entity `in_list: true` thuộc đúng nhóm đó**.
  Khai `done` mà không có entity tương ứng là **DoD FAIL**.
- Entity nhận ra nhưng KHÔNG có trong catalog ⇒ `in_list: false`, `entity_id: null`, và đưa vào
  `unlisted_candidates` — đừng bịa `entity_id`.
- `processing_metadata` phải đủ `agent_provider`, `model_used`, `timestamp` (ISO, giờ VN).

### Nạp kết quả

```bash
python scripts/l1_ingest.py data/agent_outputs_l1
```
`l1_ingest.py` tự giải nén mảng JSON gom lô, chấm DoD từng bài, ghi `l1_outputs` và chuyển
`l1_tasks.status` → `done`/`failed`, rồi archive packet đã xong.
