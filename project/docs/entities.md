# Danh sách thực thể (Entity Master List)

Cập nhật: 2026-10-22. Registry thực thể chuẩn hoá: agent `article-processor` nhận diện thực thể trong tin, matcher
đối chiếu kết quả đó (Article Lane, [design/00 §6](design/00-end-to-end-architecture.md)), lớp giao hàng định tuyến tin theo đăng ký.
Thiết kế ontology và matcher: [design/14-entity-system-and-mapping.md](design/14-entity-system-and-mapping.md).

- Sinh dữ liệu: `scripts/build_entities.py`
- Logic: `src/agent/catalog/catalog_build.py`
- Dữ liệu ra: `<DATA_ROOT>/entities/` (`paths.entities_dir()`: `entities.json`, `entities_archive.json`, `entities.csv`,
  `entities.xlsx`, `taxonomy.json`, `stats.json`)
- `entities.xlsx`: workbook đa sheet (`_Huong_dan`, `_Index`, `Securities`, `Industries`,
  `Indices`, `Exchanges`, `Nations`, `Themes`, `Assets`, `Institutions`, `Archived_Securities`) — mỗi sheet đồng nhất cột, freeze header + AutoFilter. **Người dùng
  cuối đăng ký bằng giá trị CỘT `code`** (sheet `_Huong_dan` hướng dẫn). Bảng phẳng: `entities.csv`.
- Đăng ký người dùng: `project/config/entities/users/<tên>.yaml` (mỗi người 1 file, sinh bởi `scripts/compile_users.py`)
- Resolver/matcher: `src/agent/catalog/entities.py`

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

Số liệu từ `<DATA_ROOT>/entities/stats.json` (schema 1.2.0) lúc viết; số hiện hành đọc lại tệp đó.

| type | Ý nghĩa | Số lượng (active) |
|------|---------|----------|
| `TICKER` | Cổ phiếu niêm yết (tier 1 core 742 + tier 2 extended 351) | 1093 |
| `ETF` | Quỹ ETF / quỹ mở | 28 |
| `SECURITY_OTHER` | Quỹ đóng, trái phiếu, mã phi chuẩn | 11 |
| `INDEX` | Chỉ số thị trường | 6 |
| `EXCHANGE` | Sàn giao dịch | 3 |
| `INDUSTRY_GICS1/2/3` | Ngành GICS 3 cấp | 11 / 28 / 51 |
| `MACRO_GEO` | Quốc gia, địa chính trị | 8 |
| `MACRO_THEME` | Chủ đề vĩ mô | 9 |
| `ASSET_CLASS` | Loại tài sản | 7 |
| `INSTITUTION` | Định chế, cơ quan quản lý | 7 |
| **Tổng active** | | **1262** |

Ticker tier 3 (891 mã) nằm ở `entities_archive.json` và sheet `Archived_Securities`, không vào matcher.

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
thương hiệu bổ sung tay** (`project/config/entities/brand_aliases.yaml`: `Vietcombank`, `BIDV`,
`Vingroup`, `Vietjet`…). Ví dụ: `"Tập đoàn VINGROUP - CTCP"` → `["…","VINGROUP","Vingroup"]`.
Matcher so khớp không phân biệt hoa/thường & dấu; alias chứng khoán ≥4 ký tự mới được index (ngoài
`PROTECTED_SHORT_WORDS`); alias theo miền nằm ở `project/config/entities/aliases/*.yaml`.

## Đăng ký người dùng (`project/config/entities/users/<tên>.yaml`)

> Lớp ĐĂNG KÝ/GIAO HÀNG. Nguồn nhập: `<DATA_ROOT>/subscriptions/<tên>_news.xlsx|csv`, biên dịch bằng
> `python scripts/compile_users.py`. Mỗi người dùng = 1 file, chỉ **liệt kê entity
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

### Công tắc người dùng: `<gốc dữ liệu>/subscriptions/manifest.yaml`

Một nguồn chân lý duy nhất (ADR-0026.D5) cho việc bật/tắt người dùng. Bản mẫu trong repo:
`users/subscriptions/manifest.yaml`.

```yaml
enabled: true        # false = tắt TOÀN BỘ lớp đăng ký
default: true        # trạng thái cho user chưa liệt kê (vắng tên = BẬT)
users:
  AnPT: true
  B: false           # tạm tắt B (file users/B.yaml vẫn giữ)
```

Loader dùng chung `src/core/user_manifest.py` cho `src/agent/catalog/entities.py`, `src/users/compile.py` và `pipeline_radar.py users`.
`entities._user_enabled`: `users[<tên>]` → fallback `default`; `enabled: false` tắt tất.
Thiếu file manifest → nạp tất.

## Sử dụng

```python
from src.agent.catalog.entities import load_registry
reg = load_registry()

reg.resolve_subscription("AnPT")          # -> set entity_id AnPT đăng ký
reg.subscribers_for(article_entity_ids)   # -> {tên người dùng} cần thông báo
reg.match(news_text)                      # -> nhận diện thực thể trong text (mọi loại)
```

## Chạy lại khi dữ liệu gốc đổi

```bash
python scripts/build_entities.py
# hoặc trỏ nguồn khác (mặc định --out = <DATA_ROOT>/entities):
python scripts/build_entities.py --data-root "D:/FRA - Data" --out <thư mục>
```

## Thực thể trong Article Lane

Lane L1 code-first (`l1_route.py`, `L1Runner.route_and_export`, packet `agent_tasks/l1/`) đã nghỉ hưu (ADR-0010).
Hiện hành: agent `article-processor` trả thực thể trong `article-compact-v2`; `scripts/article_expand.py`
(`src/article_lane/expand.py`) đối chiếu với matcher (`BOTH` / `LLM_ONLY` / `CODE_ONLY`) rồi ghi bản ghi
`l1-entity-output-v1`; `scripts/l1_ingest.py` nạp qua `check_l1_dod` (`src/agent/contract/l1_router.py`) như bước nạp của
`article_run.py --finish`. `code_first` không bao giờ được tính là đã phân tích.

> `EXCHANGE` (sàn) là tín hiệu yếu (mọi trang hồ sơ DN đều có "(HOSE)").

## Câu hỏi chưa giải quyết

- **Sàn theo từng mã**: dữ liệu gốc không có cột sàn (HOSE/HNX/UPCOM) cho mỗi ticker;
  hiện chỉ có 3 thực thể sàn độc lập. Nếu cần gán sàn/mã → bổ sung nguồn listing.
- **Alias thương hiệu**: đã thêm `brand_aliases.yaml` (~50 mã lớn). Mở rộng tiếp cho mid/small-cap
  khi cần.
- **11 mã `SECURITY_OTHER`** (quỹ đóng/trái phiếu như `APS12201`, `VFMVF1`) chưa gắn alias —
  xác nhận có cần đưa vào phạm vi nhận diện tin không.
- **Đăng ký người dùng**: đã theo `project/config/entities/users/<tên>.yaml`; khi scale nhiều người
  dùng động → chuyển sang bảng DB, giữ YAML làm nguồn cho nhóm ổn định.
