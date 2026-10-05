# Design 07 — Storage Layers (Medallion) + Change-Detection

Cập nhật: 2026-08-14 · Trạng thái: ĐÃ TRIỂN KHAI (producer) · Đọc kèm:
[06-raw-html-capture](06-raw-html-capture.md), [08-handoff](08-handoff-contract-catalog.md), [11-governance](11-e2e-standardization-governance.md).

Tài liệu hoá tầng lưu trữ khoa học + cơ chế log khi HTML đổi (phase-01/02).

## 1. Medallion layers
| Layer | Nơi | Bản chất | Bất biến? |
|-------|-----|----------|-----------|
| **BRONZE** | `data/raw_html/<domain>/<yyyymmdd>/<hash>.html` + `.meta.json` | raw byte-exact (đã có, doc 06) | **WORM** — không bao giờ sửa |
| **SILVER** | `data/silver/<domain>/<yyyymmdd>/<hash>.json` | clean base chuẩn hoá cho agent | derived, re-generate được |
| GOLD | — | (agent output = gold) | hoãn (YAGNI) |

`hash` = `url_title_hash` = SHA-256(url+title) = **article identity** (nhất quán mọi layer).
`content_sha256` = SHA-256(raw bytes) = **provenance/change key**.

**Nguyên tắc:** Silver là hàm THUẦN của Bronze (`SilverBuilder.build(meta, raw_bytes)`), KHÔNG
network, KHÔNG đọc DB, deterministic (built_at = meta.fetch_ts) → sửa parser/bump schema chỉ cần
`rederive_from_bronze.py`, **không re-scrape**. Raw = source of truth.

### Silver record (schemas/silver-v1.schema.json)
`{silver_schema_version, article_id, source_url, domain, content_sha256, cleaned_text,
structure{headings,paragraphs,tables,links}, images[], language, built_at, built_from_raw_path}`.
`cleaned_text` = hard field (trafilatura); `structure` = best-effort/optional.
Partition mirror Bronze → re-extract song song theo domain/ngày.

## 2. Change-detection (log khi HTML đổi để đối chiếu lần scrape sau)
Mỗi (re)capture → 1 hàng append-only trong `article_versions` (không sửa hàng cũ = audit trail).

**Ba dấu vân tay** (`src/pipeline/change_detect.py`, thuần/deterministic):
- `content_sha256` — exact (quá nhạy: ad/whitespace flip).
- `simhash64` — fuzzy near-dup của `cleaned_text` (blake2b token + weighted bit-vote 64-bit; hamming=popcount xor).
- `dom_path_sig` — chữ ký CẤU TRÚC (multiset heading-levels + bucket log-scale số p/table/link) → order/ad-insensitive.

**Phân loại (`classify`)** — ưu tiên từ trên xuống:
| State | Điều kiện | Recommendation |
|-------|-----------|----------------|
| **SELECTOR_BROKEN** | capture partial / missing main_content_node / incomplete_render | manual_review |
| **NEW** | chưa có bản trước | re_extract |
| **UNCHANGED** | `content_sha256` bằng bản trước | skip |
| **TEMPLATE_DRIFT** | `dom_path_sig` khác (CẤU TRÚC đổi) | manual_review |
| **CONTENT_CHANGED** | sha khác nhưng DOM giữ nguyên (bất kể độ lớn) | re_extract |

> Quyết định quan trọng: TEMPLATE_DRIFT **chỉ** do DOM-sig đổi — thay đổi nội dung lớn nhưng cùng
> template vẫn là CONTENT_CHANGED. (Tránh false-positive template khi bài viết chỉ dài thêm.)

**Baseline (quyết định owner 2026-08-14):** FRESH từ bây giờ — bản đầu = NEW, đối chiếu từ lần kế.
Không backfill lịch sử.

**Reconcile:** `scripts/report_drift.py` liệt kê TEMPLATE_DRIFT/SELECTOR_BROKEN → producer sửa selector
→ `rederive_from_bronze.py`. Agent (spec) treats broken/drift packages = **held** (không xử lý).

`article_versions` cols: `id, url_title_hash, source_domain, captured_at, content_sha256, simhash64,
dom_path_sig, capture_status, prev_version_id, hamming_content, dom_changed, selector_drift, state, recommendation`.
`store.changed_since(iso)` → hash có state NEW/CONTENT_CHANGED (feed catalog re-handoff).

## 3. Kiến trúc tách khỏi hot path (quyết định thiết kế)
Downstream (Silver→version→package→catalog) chạy OFFLINE qua `src/pipeline/run.process_meta` + scripts,
KHÔNG chèn vào `capture_mixin`. Lý do: giữ bất biến "scraper không ghi DB", capture nhanh, tránh tranh
chấp DB từ thread scraper, và re-derive được từ WORM Bronze. (Live wiring = opt-in tương lai.)

## 4. Refresh watch-list — nguồn "lần chụp thứ 2" (fix #1)
Change-detection chỉ có ý nghĩa khi 1 URL được capture ≥2 lần. Nhưng dedup (`seen_articles`) ở hot
path chặn re-scrape → nếu không can thiệp, mọi bài kẹt ở NEW (machinery ngủ). `src/pipeline/refresh.py`
(driver opt-in, offline) **chủ động re-fetch** watch-list URL đã biết (BỎ QUA dedup) → ghi Bronze
capture mới → `process_meta` → so version trước ⇒ UNCHANGED/CONTENT_CHANGED/TEMPLATE_DRIFT thật.
Tôn trọng robots + rate limit; KHÔNG sửa hot path. CLI: `scripts/refresh_watchlist.py [limit] [domain...]`.

## 5. Hard-gate + extraction robustness (fix #2, #3)
- **Silver validate gate:** `process_meta` validate Silver vs `silver-v1` (không chỉ work-package).
  `cleaned_text` rỗng / silver hỏng → item `held` (không giao agent). `cleaned_text` có `minLength:1`.
- **Extraction fallback chain:** `SilverBuilder._extract_cleaned` = trafilatura(high) → extract_text/BS4(medium)
  → join paragraphs(low) → empty. Ghi `extraction_quality ∈ {high,medium,low,empty}` vào Silver.
- **lang/domain hardening:** `_detect_lang` thêm `en`; `domain` fallback `source_url` netloc (strip `www.`).

## Unresolved
- Soft-404 / trang bị gỡ vs template hỏng: hiện gộp vào SELECTOR_BROKEN heuristic — tinh chỉnh khi gặp thực tế.
- Watch-list selection hiện = N bài mới nhất; có thể nâng thành theo tuổi/độ ưu tiên khi vận hành thực.
