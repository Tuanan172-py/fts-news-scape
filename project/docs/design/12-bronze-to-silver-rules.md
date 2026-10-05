# Design 12 — Quy tắc chuyển hoá Bronze → Silver

Cập nhật: 2026-08-17 · Trạng thái: RULES (chuẩn hoá đối chiếu code hiện tại) · Đọc kèm:
[06-raw-html-capture](06-raw-html-capture.md), [07-storage-layers](07-storage-layers-and-change-detection.md),
[08-handoff](08-handoff-contract-catalog.md).

Tài liệu định nghĩa **đầy đủ quy tắc/quy chế logic** để biến 1 bản ghi Bronze (raw byte-exact)
thành 1 bản ghi Silver (clean base). Bám sát code thực tế: `src/pipeline/silver_builder.py`,
`src/processor/extractor.py`, `schemas/silver-v1.schema.json`. Mục cuối liệt kê chênh lệch giữa
code hiện tại vs quy tắc mong muốn (GAP) + câu hỏi mở.

---

## 0. Định nghĩa nhanh Bronze vs Silver
| | BRONZE | SILVER |
|---|--------|--------|
| Bản chất | raw HTML byte-exact + meta capture | JSON chuẩn hoá 1-bài, sạch |
| Nơi | `data/raw_html/<domain>/<yyyymmdd>/<hash>.html` + `.meta.json` | `data/silver/<domain>/<yyyymmdd>/<hash>.json` |
| Bất biến | **WORM** — không bao giờ sửa | derived — xoá/tái tạo tự do |
| Nguồn sự thật | ✅ source of truth | ❌ dẫn xuất, phải re-derive được |
| Ai dùng | change-detection, re-derive | agent (work-package), change-detection |

`hash` = `url_title_hash` = SHA-256(url+title) = **danh tính bài** (nhất quán mọi layer).
`content_sha256` = SHA-256(raw bytes) = **khoá provenance/đổi nội dung**.

---

## 1. NGUYÊN TẮC BẤT BIẾN (INVARIANTS) — không được vi phạm

| # | Quy tắc | Vì sao | Kiểm chứng |
|---|---------|--------|-----------|
| I1 | **PURE** — `build(meta, raw_bytes)` chỉ nhận dict + bytes; KHÔNG network, KHÔNG đọc DB, KHÔNG đọc clock | tái lập được, test offline | `silver_builder.py:60` |
| I2 | **DETERMINISTIC** — cùng (meta, raw) → cùng Silver, byte-for-byte | re-derive không tạo diff giả | dùng `meta.fetch_ts`, KHÔNG `datetime.now()` |
| I3 | **RE-DERIVABLE** — sửa parser / bump schema chỉ cần chạy lại `rederive_from_bronze.py`, KHÔNG re-scrape | Bronze = source of truth | `built_at = meta.fetch_ts` `:91` |
| I4 | **KHÔNG copy byte thô** — Silver TRỎ về Bronze qua `built_from_raw_path` + `content_sha256`, không nhúng HTML gốc | tránh phình, 1 nguồn sự thật | `:92`, `:86` |
| I5 | **NON-FATAL / BEST-EFFORT** — lỗi 1 bài không được làm hỏng lô; field optional lỗi → rỗng, không throw | pipeline lô lớn phải bền | decode fallback `:63-66` |
| I6 | **ATOMIC WRITE** — ghi `.tmp` rồi `os.replace` | không để file Silver dở dang | `_atomic_write` `:96` |
| I7 | **PARTITION MIRROR BRONZE** — Silver lặp đúng partition `<domain>/<yyyymmdd>/` của Bronze | re-extract song song theo domain/ngày | `write_silver` `:103` |

> Ràng buộc: mọi quy tắc bên dưới PHẢI giữ I1–I2. Nếu 1 quy tắc cần dữ liệu ngoài (vd whitelist
> selector theo domain) → nạp qua tham số/config truyền vào, KHÔNG đọc mạng/DB trong `build`.

---

## 2. ĐẦU VÀO — kiểm kê field Bronze (`meta.json` + raw bytes)

| Field meta | Kiểu | Dùng cho Silver | Bắt buộc? |
|------------|------|-----------------|-----------|
| `source_url` | str | → `source_url` | ✅ |
| `url_title_hash` | str | → `article_id` (+ tên file) | ✅ |
| `content_sha256` | str | → `content_sha256` (provenance) | ✅ |
| `fetch_ts` | ISO8601 | → `built_at` (nguồn determinism) | ✅ |
| `html_path` | path | → `domain` (parse) + `built_from_raw_path` + `yyyymmdd` | ✅ |
| `encoding` | str | decode raw bytes | ⚠️ default `utf-8` |
| `images` | array | → `images` (pass-through hiện tại) | optional |
| `capture_status` | str | (P2 change-detect; Silver chưa dùng) | optional |
| `missing` | array | (P2 SELECTOR_BROKEN; Silver chưa dùng) | optional |
| `render_method`, `http_status`, `content_length_bytes`, `response_headers`, `error` | — | **KHÔNG map** vào Silver (thuộc provenance capture, tra ở Bronze) | — |
| raw `.html` bytes | bytes | → decode → `cleaned_text` + `structure` | ✅ |

---

## 3. ĐẦU RA — schema Silver v1 (`schemas/silver-v1.schema.json`)

**Hard field (required, gate validation chặn nếu thiếu):**
`silver_schema_version, article_id, source_url, domain, content_sha256, cleaned_text, built_from_raw_path`.

**Soft field (optional, best-effort):**
`built_at, language, structure{headings,paragraphs,tables,links}, images[]`.

Quy ước: **`cleaned_text` = hard** (không có ⇒ Silver vô dụng cho agent) · **`structure`/`images` = best-effort**
(lỗi/bẩn không chặn gate, nhưng phải tuân quy tắc lọc §7–§8).

---

## 4. BẢNG ÁNH XẠ FIELD-BY-FIELD + QUY TẮC

| Silver field | Nguồn | Quy tắc chuyển | Ref code |
|--------------|-------|----------------|----------|
| `silver_schema_version` | hằng | = `"1.0"`; bump khi đổi logic bóc tách (§11) | `:19,58` |
| `article_id` | `meta.url_title_hash` | copy thẳng; nếu rỗng → **FAIL gate** (không có danh tính) | `:83` |
| `source_url` | `meta.source_url` | copy thẳng (giữ query string nguyên bản, KHÔNG strip utm ở Silver) | `:68,84` |
| `domain` | `meta.html_path` | parse segment sau `raw_html/`; fallback `"unknown"` | `:73-80` |
| `content_sha256` | `meta.content_sha256` | copy thẳng (khoá provenance, KHÔNG tự tính lại) | `:86` |
| `cleaned_text` | raw bytes | decode → trafilatura → fallback (§6) | `:69-70` |
| `structure` | raw bytes | BeautifulSoup parse (§7) | `:88` |
| `images` | `meta.images` | pass-through (§8 — CẦN lọc) | `:89` |
| `language` | `cleaned_text` | heuristic ký tự VN (§9) | `:90` |
| `built_at` | `meta.fetch_ts` | copy thẳng — **KHÔNG dùng now()** (I2) | `:91` |
| `built_from_raw_path` | `meta.html_path` | copy thẳng (con trỏ ngược Bronze) | `:92` |

---

## 5. QUY TẮC CHUẨN HOÁ (NORMALIZATION)

| # | Quy tắc | Hiện trạng |
|---|---------|-----------|
| N1 | **Decode**: dùng `meta.encoding`; lỗi `LookupError/TypeError` → `utf-8`; luôn `errors="replace"` (không throw) | ✅ `:62-66` |
| N2 | **Whitespace**: text field dùng `get_text(" ", strip=True)` — gộp khoảng trắng, trim đầu/cuối | ✅ `_parse_structure` |
| N3 | **Unicode NFC**: chuẩn hoá `unicodedata.normalize("NFC", …)` cho `cleaned_text` + text structure | ❌ GAP (§12 G1) |
| N4 | **Loại control char** (`\x00-\x08`, `\x0b\x0c`, `\x0e-\x1f`) khỏi text | ❌ GAP |
| N5 | **Chuẩn hoá xuống dòng**: `\r\n`/`\r` → `\n`; gộp ≥3 `\n` → 2 | ❌ GAP (trafilatura xử lý phần lớn) |
| N6 | **KHÔNG chuẩn hoá URL** trong `source_url`/`links.href` (giữ nguyên bản để agent tự quyết) | ✅ mặc định |

> N3–N5 cần bổ sung để `simhash64` (P2) ổn định & so khớp text đáng tin. Tất cả thuần → giữ I1–I2.

---

## 6. QUY TẮC BÓC `cleaned_text` (trường HARD)

Chuỗi fallback (dừng ở bước đầu ra text khác rỗng):
1. `trafilatura.extract(html, output_format=txt, include_tables=True, include_images=False, include_links=False, include_comments=False)` — bóc body chính, bỏ nav/ad/comment. (`extractor.py:13-19`)
2. Fragment fail → wrap `<html><body>…</body></html>` rồi extract lại. (`extractor.py:56-58`)
3. Cuối cùng → `BeautifulSoup(...).get_text(" ", strip=True)` (thô nhưng không rỗng). (`extractor.py:60-61`)

Quy tắc:
- C1: `cleaned_text` **phải phản ánh THÂN BÀI**, không lẫn menu/footer (trafilatura đảm nhận — xác nhận sample sạch).
- C2: Nếu cả 3 bước → rỗng ⇒ đặt `cleaned_text=""` và **đánh dấu để gate xử lý** (empty-body = ứng viên SELECTOR_BROKEN ở P2, KHÔNG throw ở Silver — I5).
- C3: `include_tables=True` (giữ số liệu tài chính); `include_links/images=False` (link/ảnh nằm ở `structure`/`images`).

---

## 7. QUY TẮC `structure` (best-effort DOM)

Hiện `_parse_structure` (`:32-54`) lấy **toàn bộ** `h1-h6 / p / table / a[href]` trong `<body>` → **kéo cả boilerplate**
(menu điều hướng, "CÙNG CHUYÊN MỤC", bài liên quan, địa chỉ toà soạn, copyright — thấy rõ trong sample cafef).

Quy tắc mong muốn:
- S1: **headings**: giữ `{level, text}`, bỏ heading rỗng (✅ đã có), bỏ heading thuộc khối nav/aside/footer (❌ GAP).
- S2: **paragraphs**: chỉ lấy `<p>` trong vùng thân bài; loại footer (địa chỉ/điện thoại/email/copyright/giấy phép) & label ("MỚI NHẤT!", dòng tác giả|ngày|chuyên mục) (❌ GAP).
- S3: **tables**: mỗi table = mảng hàng, mỗi hàng = mảng cell (`th|td`), bỏ hàng rỗng (✅ đã có).
- S4: **links**: `{href, text}`; bỏ `href` rác (`javascript:;`, `#`, rỗng); phân biệt link nội dung vs link điều hướng (❌ GAP — hiện gom hết).
- S5: **Nguyên tắc scope**: ưu tiên node thân bài (giao với vùng trafilatura bóc) thay vì cả `<body>`. Cân nhắc drop `paragraphs` (đã có `cleaned_text`) để tránh trùng lặp & boilerplate.
- S6: `structure` là OPTIONAL — parse lỗi ⇒ trả `{}` hoặc mảng rỗng, KHÔNG chặn gate.

> Thảo luận: `structure` chủ yếu phục vụ `dom_path_sig` (P2 phát hiện template-drift) + tiện agent tra cứu.
> Cho mục đích drift, boilerplate ổn định KHÔNG hại (sig vẫn ổn định). Cho agent, boilerplate là nhiễu.
> ⇒ Quyết định (mở, §12 Q1): lọc boilerplate cho agent VÀ giữ 1 chữ ký cấu trúc thô riêng cho P2.

---

## 8. QUY TẮC `images`

Hiện copy nguyên `meta.images` (`:89`) → gồm ảnh cover, ảnh thân bài, **ảnh thumbnail bài-liên-quan** + logo VCCorp (thấy trong sample).

Quy tắc mong muốn:
- IMG1: giữ trường `{resolved_url, alt, title, caption}`; bỏ `outer_tag` thô (chỉ cần khi debug).
- IMG2: lọc ảnh KHÔNG thuộc thân bài: logo, icon, thumbnail bài liên quan (heuristic: ảnh có `alt` trùng tiêu đề bài khác / kích thước nhỏ `zoom/223_140` / domain logo).
- IMG3: khử trùng theo `resolved_url`.
- IMG4: best-effort — lỗi ⇒ `images=[]`, không chặn gate.

> GAP: hiện chưa lọc (§12 G3). Ảnh liên quan/logo lọt vào Silver = nhiễu cho agent.

---

## 9. QUY TẮC `language`

- L1: heuristic hiện tại — đếm ký tự đặc trưng VN trong 2000 ký tự đầu `cleaned_text`; ≥5 ⇒ `"vi"`, else `"und"`. (`:25-29`)
- L2: OPTIONAL — không chặn gate; `und` hợp lệ.
- L3 (mở): nếu cần đa ngôn ngữ (en/zh…) → nâng lên lib `langdetect`/`fasttext`. Hiện KISS đủ (nguồn chủ yếu tiếng Việt).

---

## 10. QUY TẮC PROVENANCE, PARTITION & GHI FILE

- P1: `built_at = meta.fetch_ts` (I2). Cấm `now()`.
- P2: `built_from_raw_path = meta.html_path` — con trỏ ngược 1-1 tới Bronze.
- P3: partition ghi = `data/silver/<domain>/<yyyymmdd>/<article_id>.json`; `yyyymmdd` lấy từ segment áp chót của `built_from_raw_path`; fallback `unknown-date`. (`write_silver:103-114`)
- P4: ghi atomic (`.tmp`→`os.replace`), UTF-8, `ensure_ascii=False`, `indent=2`. (`:114`)
- P5: **idempotent** — re-derive cùng Bronze GHI ĐÈ đúng path, nội dung không đổi (I2 đảm bảo).

---

## 11. QUY TẮC VERSIONING & RE-DERIVE

- V1: đổi BẤT KỲ logic bóc tách (normalize, lọc boilerplate, filter ảnh…) ⇒ **bump `silver_schema_version`**.
- V2: sau bump ⇒ chạy `scripts/rederive_from_bronze.py` dựng lại toàn bộ Silver từ Bronze WORM (KHÔNG re-scrape).
- V3: re-derive PHẢI cho kết quả xác định; diff Silver trước/sau chỉ phản ánh thay đổi logic, không phải noise thời gian.
- V4: Bronze bất biến ⇒ mọi phiên bản Silver luôn tái lập được từ lịch sử.

---

## 12. CHÊNH LỆCH CODE HIỆN TẠI vs QUY TẮC (GAP) + rủi ro

| ID | Gap | Ảnh hưởng | Ưu tiên |
|----|-----|-----------|---------|
| G1 | Chưa NFC + strip control char (N3–N4) | simhash64 kém ổn định, so text sai lệch | Cao |
| G2 | `structure` kéo boilerplate nav/footer/related (S1–S5) | nhiễu cho agent; sample lẫn địa chỉ/copyright | Cao |
| G3 | `images` chưa lọc ảnh liên quan/logo (IMG2) | agent nhận ảnh sai ngữ cảnh | Trung |
| G4 | `images` còn giữ `outer_tag` thô (IMG1) | phình file, lộ HTML thô vào Silver | Thấp |
| G5 | Empty-body chưa gắn cờ (C2) | body rỗng lọt xuống agent thay vì hold | Trung |
| G6 | `structure.paragraphs` trùng `cleaned_text` (S5) | dữ liệu đôi, tăng kích thước | Thấp |
| G7 | Chưa tách "chữ ký cấu trúc thô cho P2" vs "structure sạch cho agent" (§7 thảo luận) | lọc boilerplate có thể làm dom_path_sig kém nhạy drift | Trung |

---

## 13. LƯU ĐỒ QUY TẮC (tóm tắt 1 hình)
```
Bronze(meta.json + raw.html)
  │  I1 pure · I2 deterministic
  ├─ decode(meta.encoding, errors=replace)                     [N1]
  ├─ cleaned_text = trafilatura → wrap → bs4.get_text          [C1-C3]  (HARD)
  │      └─ normalize NFC + strip ctrl + newline               [N3-N5]  (GAP G1)
  ├─ structure = bs4(h/p/table/a)                              [S1-S6]
  │      └─ lọc boilerplate nav/footer/related                 (GAP G2)
  ├─ images = meta.images → lọc related/logo → dedup           [IMG1-4] (GAP G3-4)
  ├─ language = heuristic VN                                   [L1-L3]
  ├─ domain/built_at/built_from_raw_path/content_sha256 = copy [P1-P2]  (provenance)
  ▼
  gate: required hard fields đủ? ─no─► reject (log, KHÔNG throw lô) [I5]
  ▼ yes
  write_silver(): partition mirror + atomic + idempotent      [P3-P5,I6-I7]
  ▼
Silver(.json)  ──► P2 change-detect ──► P3 work-package ──► agent
```

---

## Câu hỏi chưa giải quyết
1. **Q1 (§7/G7):** Lọc boilerplate khỏi `structure` cho agent CÓ phá độ nhạy `dom_path_sig` (P2) không? → nên tách 2 chữ ký (structure sạch cho agent + raw-structure-sig cho drift) hay giữ 1?
2. **Q2 (C2/G5):** Ngưỡng "empty/too-short body" để gắn cờ hold là bao nhiêu ký tự? Định nghĩa ở Silver hay để P2 quyết dựa `capture_status/missing`?
3. **Q3 (IMG2):** Heuristic lọc ảnh liên quan có cần whitelist/blacklist theo domain (truyền qua config, giữ I1) không?
4. **Q4 (§11):** Bump `silver_schema_version` lên `1.1` hay `2.0` khi áp G1–G3? (minor vs breaking cho consumer P3/P4).
5. **Q5 (N6):** Có chuẩn hoá bỏ `utm_*` khỏi `source_url` ở Silver không, hay giữ nguyên và để agent tự xử?
