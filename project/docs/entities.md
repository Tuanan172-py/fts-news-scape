# Danh sách thực thể (Entity Master List) — lớp L3 agent

Registry thực thể chuẩn hoá để lớp **L3 agent nhận diện đối tượng trong tin tức**.
Người dùng chỉ cần *config nhóm đối tượng* → agent trả về tin khớp đúng nhóm.

- Sinh dữ liệu: `scripts/build_entities.py`
- Dữ liệu ra: `data/entities/` (`entities.json`, `entities.csv`, `entities.xlsx`, `taxonomy.json`, `stats.json`)
- `entities.xlsx`: workbook đa sheet (`_Index`, `Securities`, `Industries`, `Sectors_FPA`,
  `Indices`, `Exchanges`) — mỗi sheet đồng nhất cột, freeze header + AutoFilter.
  Bảng phẳng toàn cục để filter: dùng `entities.csv`.
- Config nhóm: `config/entities/entity_groups.yaml`
- Resolver/matcher: `src/agent/entities.py`

## Nguồn dữ liệu gốc (`FRA - Data/`)

| Lớp input | File | Rút ra thực thể |
|-----------|------|-----------------|
| Mã (ticker) | `trading_data/market_caps.parquet`, `os.xlsx` | mã cổ phiếu, số CP lưu hành |
| Chỉ số | `trading_data/indices.parquet` | 6 chỉ số (VN-Index, VN30, …) |
| Tên doanh nghiệp | `company_data/company_name.xlsx` | tên chính thức + alias |
| Quỹ ETF | `company_data/etf_name.xlsx` | ETF |
| Ngành | `industry_classification/industry_classification.xlsx` | GICS 3 cấp |
| Nhóm ngành FPA | `APD_Data_Industry/data/<sector>/` | nhóm ngành phân tích |

Sàn (HOSE/HNX/UPCOM) là tập tĩnh suy ra từ chỉ số (dữ liệu gốc không có cột sàn/mã).

## Loại thực thể & số lượng

| type | Ý nghĩa | Số lượng |
|------|---------|----------|
| `TICKER` | Cổ phiếu niêm yết (mã 3 ký tự) | 1981 |
| `ETF` | Quỹ ETF / quỹ mở | 28 |
| `SECURITY_OTHER` | Quỹ đóng, trái phiếu, mã phi chuẩn | 11 |
| `INDEX` | Chỉ số thị trường | 6 |
| `EXCHANGE` | Sàn giao dịch | 3 |
| `INDUSTRY_GICS1/2/3` | Ngành GICS 3 cấp | 11 / 28 / 51 |
| `SECTOR_FPA` | Nhóm ngành phân tích FPA | 16 |
| **Tổng** | | **2135** |

## Schema mỗi thực thể

```json
{
  "entity_id": "TICKER:HPG",              // khoá chính duy nhất, namespaced theo type
  "type": "TICKER",
  "code": "HPG",                          // mã gốc
  "canonical_name": "CTCP Tập đoàn Hòa Phát",
  "aliases": ["CTCP Tập đoàn Hòa Phát", "Hòa Phát"],  // surface form để match text
  "attributes": {                         // thuộc tính nhận dạng, theo type
    "gics1": "Nguyên vật liệu", "gics2": "Kim loại & Khai khoáng", "gics3": "Thép",
    "shares_outstanding": 8442964480, "has_market_cap": true, "listed_universe": true
  },
  "sources": ["company_data/company_name.xlsx", "..."]   // truy vết nguồn
}
```

## Ánh xạ tiêu chí (yêu cầu)

- **Unique** — `entity_id` namespaced (`TICKER:HPG`), không trùng (đã kiểm).
- **Rõ ràng & cụ thể** — mỗi thực thể có `canonical_name` + `type` + `aliases`.
- **Nhất quán** — mọi thực thể cùng schema; ngành GICS2→GICS1 nhất quán 100%.
- **Có thuộc tính nhận dạng** — `code` + `aliases` (+ GICS/exchange).
- **Tránh dư thừa** — mã cổ phiếu & tên doanh nghiệp **gộp làm một** thực thể
  (tên là thuộc tính), không tách `COMPANY` riêng.

## Alias (nhận diện trong tin tức)

`aliases` = `[tên đầy đủ, tên rút gọn]`. Tên rút gọn cắt tiền tố pháp lý
(`CTCP`, `Ngân hàng TMCP`, `Tổng Công ty`, `Tập đoàn`, `Quỹ ETF`…):
`"CTCP Tập đoàn Hòa Phát"` → `"Hòa Phát"`. Matcher so khớp không phân biệt hoa/thường & dấu.

## Config nhóm đối tượng (`entity_groups.yaml`) — BƯỚC SAU (đăng ký), tách khỏi L1

> Đây là lớp ĐĂNG KÝ/THÔNG BÁO, **độc lập** với L1. L1 chỉ nhận diện entity thô; việc gom
> entity → nhóm người dùng quan tâm là bước sau khi có đăng ký thật. `fta`/`co_ban`/`watch_bluechip`
> hiện chỉ là **ví dụ khung**, chưa phải nhóm thật.

Người dùng khai báo nhóm bằng cách cộng dồn (union) các luật chọn:
`include_types`, `include_gics1`, `include_sectors`, `include_entities`, `exclude_entities`.
Ánh xạ entity→nhóm: `registry.groups_for(entity_ids)`.

## Sử dụng (L3 agent)

```python
from src.agent.entities import load_registry
reg = load_registry()

reg.resolve_group("co_ban")            # -> set entity_id thuộc nhóm
reg.match(news_text, group="co_ban")   # -> list thực thể nhận diện, đã lọc theo nhóm
reg.match(news_text)                   # -> nhận diện toàn bộ (mọi loại)
```

## Chạy lại khi dữ liệu gốc đổi

```bash
python scripts/build_entities.py
# hoặc trỏ nguồn khác:
python scripts/build_entities.py --data-root "D:/FRA - Data" --out data/entities
```

## Lớp L1 — nhận diện entity theo tiêu đề (quy trình 2 tầng)

Nhiệm vụ L1: mỗi tin nhận về → nhận diện thực thể trong **tiêu đề** (chưa xử lý body).
Quy trình **code-first → handoff** (KHÔNG phụ thuộc nhóm đăng ký; map nhóm là bước sau).

```
title ─► TẦNG 1  code-first  (src/agent/l1_classifier.detect)  khớp mã + alias
          │  khớp ≥1 entity ─► RESOLVED (tag thẳng: entities + industries suy từ GICS)
          └─ không khớp     ─► NEEDS_AGENT
                                └─► TẦNG 2  handoff (src/agent/l1_router)
                                     build task-packet ─► [AGENT L1] ─► l1-entity-output-v1
                                        ─► check_l1_dod (schema + grounding + checklist)
```

**Tầng 1 — code-first** (`l1_classifier.classify_article`): khớp mã (in hoa, trừ stoplist)
+ alias tên (fold dấu); suy ngành từ GICS của mã. Output có `needs_agent` (True ⇔ không khớp).

**Tầng 2 — handoff cho agent** (`l1_router`):
- `route_article()` → `route ∈ {resolved, needs_agent}`.
- `build_l1_task_packet()` → gói self-describing (title + trỏ `entities.json`/`taxonomy.json`
  + output_contract + checklist), ghi `data/agent_tasks/l1/<id>.task.json`.
- Agent đọc **system prompt + checklist**: `schemas/l1-entity-instructions-v1.md`.
- Agent nộp output theo `schemas/l1-entity-output-v1.schema.json`; gác bằng
  `check_l1_dod()` (schema + surface/citation ⊂ title + checklist `categories` nhất quán).

**Checklist agent** (`categories`, mỗi nhóm ∈ `done|none|out_of_list`):
`ticker_company` · `etf_fund` · `index` · `exchange` · `industry_sector`
→ biết nhóm nào **thực hiện được**, nhóm nào **không** (và `out_of_list` = cần bổ sung danh sách).

**Chạy** (kho silver → split):
```bash
python scripts/l1_route.py
# resolved (code-first) -> data/agent_tasks/l1/resolved.jsonl
# needs_agent (handoff) -> data/agent_tasks/l1/<article_id>.task.json
```

**Đo trên 153 silver**: code-first **resolved 86 / 153 (56%)**; **needs_agent 67** → handoff.
Ví dụ handoff đúng: tiêu đề "...của **Vingroup**..." bị code bỏ sót (alias VIC là tên pháp lý
đầy đủ, không phải thương hiệu "Vingroup") → chuyển agent nhận diện ngữ nghĩa. Đây cũng là
lý do nên mở rộng alias thương hiệu (xem "Câu hỏi chưa giải quyết") để giảm tải agent.

> `EXCHANGE` (sàn) là tín hiệu yếu (mọi trang hồ sơ DN đều có "(HOSE)") — instructions yêu cầu
> agent KHÔNG chấm `exchange=done` cho phần "(HOSE)" trong tên trang hồ sơ.

## Câu hỏi chưa giải quyết

- **Sàn theo từng mã**: dữ liệu gốc không có cột sàn (HOSE/HNX/UPCOM) cho mỗi ticker;
  hiện chỉ có 3 thực thể sàn độc lập. Nếu cần gán sàn/mã → bổ sung nguồn listing.
- **Alias mở rộng**: mới sinh tên đầy đủ + rút gọn. Có thể thêm tên tiếng Anh,
  tên thương hiệu, viết tắt (vd "Vietcombank") nếu có nguồn.
- **11 mã `SECURITY_OTHER`** (quỹ đóng/trái phiếu như `APS12201`, `VFMVF1`) chưa gắn alias —
  xác nhận có cần đưa vào phạm vi nhận diện tin không.
