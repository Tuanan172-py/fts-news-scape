# Danh sách thực thể (Entity Master List) — lớp L3 agent

Registry thực thể chuẩn hoá để lớp **L3 agent nhận diện đối tượng trong tin tức**.
Người dùng chỉ cần *config nhóm đối tượng* → agent trả về tin khớp đúng nhóm.

- Sinh dữ liệu: `scripts/build_entities.py`
- Dữ liệu ra: `data/entities/` (`entities.json`, `entities.csv`, `entities.xlsx`, `taxonomy.json`, `stats.json`)
- `entities.xlsx`: workbook đa sheet (`_Huong_dan`, `_Index`, `Securities`, `Industries`,
  `Indices`, `Exchanges`) — mỗi sheet đồng nhất cột, freeze header + AutoFilter. **Người dùng
  cuối đăng ký bằng giá trị CỘT `code`** (sheet `_Huong_dan` hướng dẫn). Bảng phẳng: `entities.csv`.
- Đăng ký người dùng: `config/entities/users/<tên>.yaml` (mỗi người 1 file)
- Resolver/matcher: `src/agent/entities.py`

## Nguồn dữ liệu gốc (`FRA - Data/`)

| Lớp input | File | Rút ra thực thể |
|-----------|------|-----------------|
| Mã (ticker) | `trading_data/market_caps.parquet`, `os.xlsx` | mã cổ phiếu, số CP lưu hành |
| Chỉ số | `trading_data/indices.parquet` | 6 chỉ số (VN-Index, VN30, …) |
| Tên doanh nghiệp | `company_data/company_name.xlsx` | tên chính thức + alias |
| Quỹ ETF | `company_data/etf_name.xlsx` | ETF |
| Ngành | `industry_classification/industry_classification.xlsx` | GICS 3 cấp |

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
| **Tổng** | | **2119** |

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

`aliases` gồm: tên đầy đủ → tên rút gọn (cắt tiền tố + đuôi pháp lý: `CTCP`, `Ngân hàng TMCP`,
`Tổng Công ty`, `Tập đoàn`, `- CTCP`…) → thương hiệu trong ngoặc (`(CHOLIMEX)`) → **alias
thương hiệu bổ sung tay** (`config/entities/brand_aliases.yaml`: `Vietcombank`, `BIDV`,
`Vingroup`, `Vietjet`…). Ví dụ: `"Tập đoàn VINGROUP - CTCP"` → `["…","VINGROUP","Vingroup"]`.
Matcher so khớp không phân biệt hoa/thường & dấu; alias ≥4 ký tự mới được index.

## Đăng ký người dùng (`config/entities/users/<tên>.yaml`) — BƯỚC SAU (thông báo)

> Lớp ĐĂNG KÝ/THÔNG BÁO, **độc lập** với L1. Mỗi người dùng = 1 file, chỉ **liệt kê entity
> quan tâm theo từng nhóm** (không kèm metadata). Tên file = tên người dùng.

**Quy chuẩn: mọi giá trị lấy từ CỘT `code` trong `entities.xlsx`.**

```yaml
# config/entities/users/AnPT.yaml
tickers:    [HPG, FPT, VCB, VNM, MWG]      # code cổ phiếu/ETF -> TICKER/ETF/…:<code>
etfs:       [E1VFVN30]                      # code quỹ ETF      -> ETF:<code>
indices:    [VNINDEX, VN30]                 # code chỉ số       -> INDEX:<code>
exchanges:  [HOSE]                          # code sàn          -> EXCHANGE:<code>
industries: [THEP, NGAN_HANG]              # code ngành GICS   -> INDUSTRY_GICS*:<code>
entities:   [TICKER:HPG]                    # (tuỳ chọn) entity_id nguyên bản — cửa thoát
```

Loader đọc mọi file trong `users/`, ánh xạ mỗi nhóm → `entity_id` (industries nhận **code**
ngành GICS như THEP/NGAN_HANG, KHÔNG theo tên; báo `subscription_warnings` nếu sai). Ánh xạ tin→người đăng ký:
`registry.subscribers_for(entity_ids)`.

## Sử dụng

```python
from src.agent.entities import load_registry
reg = load_registry()

reg.resolve_subscription("AnPT")          # -> set entity_id AnPT đăng ký
reg.subscribers_for(article_entity_ids)   # -> {tên người dùng} cần thông báo
reg.match(news_text)                      # -> nhận diện thực thể trong text (mọi loại)
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
work_package/silver ─► scripts/l1_route.py (L1Runner)
   TẦNG 1 code-first (l1_classifier)  khớp mã + alias → suy ngành từ GICS
      ├─ resolved  (khớp ≥1 entity)
      └─ needs_agent (code không khớp)
   → lưu DB l1_tasks (code_first + route + status=pending)
   → phát task-packet data/agent_tasks/l1/<id>.task.json  (nhúng code_first để AUDIT)
        └─► [CRON kích hoạt AGENT của bạn — prompt theo l1-entity-instructions-v1.md]
             → l1-entity-output-v1 (*.json)
             → scripts/l1_ingest.py (L1Runner.ingest) → check_l1_dod
                 → l1_outputs + l1_tasks.status = done/failed
```

**Tầng 1 — code-first** (`l1_classifier.classify_article`): khớp mã (in hoa, trừ stoplist)
+ alias tên (fold dấu); suy ngành từ GICS của mã. `needs_agent=True` ⇔ không khớp.

**Tầng 2 — handoff + AUDIT** (`l1_router` + `l1_runner`):
- `route_and_export()` → lưu `l1_tasks` (code-first + route) + phát task-packet.
  `--review all` (mặc định) phát packet cho MỌI tin để **agent có quyền tra soát** cả tin
  resolved; `--review missed` chỉ phát cho `needs_agent`.
- Packet self-describing: `input.title` + trỏ `entities.json`/`taxonomy.json` +
  **`input.code_first`** (để agent xác nhận/sửa/bổ sung) + `output_contract` + checklist.
- Agent đọc **system prompt + checklist**: `schemas/l1-entity-instructions-v1.md`.
- Ingest gác bằng `check_l1_dod()`: schema `l1-entity-output-v1` + surface/citation ⊂ title +
  `categories` nhất quán → `l1_tasks.status = done/failed` (idempotent theo article_id).

**Checklist agent** (`categories`, mỗi nhóm ∈ `done|none|out_of_list`):
`ticker_company` · `etf_fund` · `index` · `exchange` · `industry_sector`
→ biết nhóm nào **thực hiện được**, nhóm nào **không** (`out_of_list` = có nhắc nhưng ngoài
danh sách → `unlisted_candidates`, tín hiệu cần bổ sung).

**Chạy**:
```bash
python scripts/l1_route.py                 # code-first + phát packet (DB l1_tasks)
python scripts/l1_route.py --review missed # chỉ handoff tin code không khớp
python scripts/l1_ingest.py data/agent_outputs_l1/   # nạp output agent → DoD → done/failed
```

**Đo trên 153 silver (sau khi mở rộng alias thương hiệu)**: code-first **resolved 94 / 153
(61%)**; **needs_agent 59** → handoff. Alias thương hiệu (`config/entities/brand_aliases.yaml`:
Vingroup→VIC, Vietcombank→VCB, BIDV→BID, Vietjet→VJC…) giúp code khớp thêm, giảm tải agent.

> `EXCHANGE` (sàn) là tín hiệu yếu (mọi trang hồ sơ DN đều có "(HOSE)") — instructions yêu cầu
> agent KHÔNG chấm `exchange=done` cho phần "(HOSE)" trong tên trang hồ sơ.
>
> **Nối pipeline**: `l1_route.py` là bước deterministic, thêm vào cron/orchestrator ngay sau
> khi build work_packages. Chỉ còn cron kích hoạt agent + `l1_ingest.py` là khép kín.

## Câu hỏi chưa giải quyết

- **Sàn theo từng mã**: dữ liệu gốc không có cột sàn (HOSE/HNX/UPCOM) cho mỗi ticker;
  hiện chỉ có 3 thực thể sàn độc lập. Nếu cần gán sàn/mã → bổ sung nguồn listing.
- **Alias thương hiệu**: đã thêm `brand_aliases.yaml` (~50 mã lớn). Mở rộng tiếp cho mid/small-cap
  khi cần (agent L1 tạm thời bù phần code bỏ sót qua `unlisted_candidates`).
- **11 mã `SECURITY_OTHER`** (quỹ đóng/trái phiếu như `APS12201`, `VFMVF1`) chưa gắn alias —
  xác nhận có cần đưa vào phạm vi nhận diện tin không.
- **Đăng ký người dùng**: đã theo `config/entities/users/<tên>.yaml`; khi scale nhiều người
  dùng động → chuyển sang bảng DB, giữ YAML làm nguồn cho nhóm ổn định. Nối `subscribers_for()`
  vào notifier là bước tiếp.
