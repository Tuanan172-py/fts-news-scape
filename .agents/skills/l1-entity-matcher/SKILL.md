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
