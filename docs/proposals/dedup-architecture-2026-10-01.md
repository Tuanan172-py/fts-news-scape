# Đề xuất kiến trúc xử lý bài trùng lặp đa nguồn (2026-10-01)

> Trạng thái: **đã duyệt và triển khai một phần (2026-10-02, ADR 0013 và ADR 0016, story US-033)**. Đã làm: C1 đến C5 của §9, P1 và P2. Chưa làm: P3 (chế độ chênh), P4 (embedding) và gộp dòng theo cụm ở giao hàng. Xem `docs/OPEN-ITEMS.md` mục CAP-1.
> Số đo lấy từ `C:\data\news-scape\monocle.db` (chỉ đọc), cửa sổ 3 ngày 28/09–01/10, 1.759 bài trong `articles`, 2.074 hàng trong `seen_articles`. Script đo nằm ngoài kho (scratchpad), có thể đưa vào `scripts/` ở P0.

## 0. Chốt của người dùng (2026-10-01, vòng 2)

1. **Không xoá bài trùng.** Bài xác định là trùng thì không cần qua bước LLM. Bài đó kế thừa kết quả của bài gốc và vẫn nằm trong kho với đủ nguồn, thời điểm và URL.
2. **Trùng lặp là tín hiệu đầu tư.** Một chủ đề được nhiều tờ báo đăng đi đăng lại với tần suất cao là dấu hiệu của sentiment và mức độ chú ý. Cụm trùng vì vậy là **đầu vào phân tích**, không phải rác cần dọn. Xem §8 và `docs/proposals/insight-analytics-2026-10-01.md`.
3. **Thu thập trọn vẹn, xử lý về sau.** Đã ghim thành ADR 0013 và rule 10. Mục P0 dưới đây là phần thực thi đầu tiên của nguyên tắc này. Kiến trúc tầng thu thập ở §9.

## 1. Kết luận

1. **Không chọn "code" hay "LLM" cho cả bài toán.** Trùng lặp có 5 loại khác nhau. Ba loại là việc **cơ học** (cùng URL, cùng nội dung, chép lại): code làm, 0 token, quyết định luôn. Hai loại là việc **ngữ nghĩa** (cùng sự kiện viết khác, bản cập nhật có tin mới): code chỉ đề cử ứng viên, LLM quyết định. Ranh giới này trùng đúng ranh giới AGENTS.md §6.C đã đặt.
2. **"Gộp cụm, không xoá."** Không bài nào bị bỏ. Mỗi bài thuộc một cụm câu chuyện (`story_cluster`) với vai trò rõ ràng. Vai trò quyết định bài được phân tích đầy đủ, phân tích phần chênh, hay kế thừa kết quả. Token chỉ chi cho thông tin mới.
3. **Việc gấp nhất không phải thêm chống trùng mà là sửa chống trùng đang có.** Lớp cào hiện loại bài trước khi lưu, không để lại dấu vết. Trong 3 ngày nó loại 439 bài, trong đó **202 bài (46%) bị loại nhầm**. Các bài này mất hẳn: không có Bronze, không có URL để cào lại.

## 2. Số đo thực tế

### 2.1. Chống trùng hiện có

| Lớp                           | Nơi                                 | Cơ chế                             | Hành vi                                                                                                            |
| ------------------------------ | ------------------------------------ | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| SimHash nội dung              | `src/pipeline/change_detect.py:22` | SimHash64 trên văn bản sạch      | chỉ dùng để phát hiện bài**tự thay đổi** giữa hai lần chụp, không dùng để so giữa các bài |
| Agent`story-dedup-clusterer` | `.agents/registry.yaml:275`        | thiết kế cho lane Gold đã ngừng | `draft`, chưa từng chạy                                                                                        |

### 2.2. Lớp cào đang loại nhầm

439 bài bị loại trong 3 ngày (21% số bài đã thấy). Đối chiếu lại từng bài với tiêu đề gây ra việc loại:

| Phân loại                                                 |      Số bài | Ví dụ                                                                                              |
| ----------------------------------------------------------- | ------------: | ---------------------------------------------------------------------------------------------------- |
| Trùng thật (`ratio ≥ 85`)                              |           182 | cùng tin "VPB: Nghị quyết HĐQT…" trên cafef RSS và cafef capture                              |
| Gần như trùng (`ratio 60–85`)                         |            50 | "Đề xuất chuyển tiền quỹ bình ổn xăng dầu…"                                               |
| **Loại nhầm** (`token_set` = 100, `ratio` < 60) | **202** | "Giá vàng 'sập' mạnh sau 1 tháng" bị coi là trùng với tiêu đề**"1"** của baodautu |
| Không khớp mờ                                            |             5 |                                                                                                      |

Ba lỗi gốc chồng lên nhau:

1. `token_set_ratio` trả 100 khi tập từ của chuỗi ngắn nằm trọn trong chuỗi dài. Tiêu đề càng ngắn, càng dễ "trùng" với mọi thứ.
2. Bộ cào baodautu sinh tiêu đề hỏng chỉ có `"1"`, `"2"`. Một tiêu đề hỏng làm mọi bài chứa chữ số "1" trong 48 giờ sau đó bị loại.
3. Ngay cả trong nhóm `ratio ≥ 85` vẫn có nhầm theo mẫu: "GAS: nghị quyết HĐQT số 110 ngày 25/09" bị coi là trùng với "MWG: nghị quyết HĐQT số 12 ngày 25/09". Hai công ty khác nhau, ratio 92.

Lỗi phụ: `seen_articles.source_domain` ghi lẫn `cafef` và `cafef.vn`, nên `exclude_domain` không loại được trường hợp cùng một trang so với chính nó qua hai bộ cào.

### 2.3. Trùng còn lọt vào `articles`

Đo trùng nội dung bằng shingle 5 từ, bỏ shingle khuôn mẫu (xuất hiện ở trên 2% số bài), tính tỷ lệ chứa (containment) giữa hai bài:

| Ngưỡng containment              |  Cụm thừa | Tỷ lệ |
| --------------------------------- | ----------: | ------: |
| ≥ 0,8 (bản sao, chép lại)     |  67 / 1.742 |    3,8% |
| ≥ 0,5 (gồm cả cùng sự kiện) | 136 / 1.742 |    7,8% |

Các dạng quan sát được:

- **Cùng bài, khác URL** (9 cặp, toàn cafef): `…-188260923233056032.chn?utm_source=du-lieu` và `…-188260923233056032.chn`. Có cả trường hợp cùng mã bài, khác slug. `url_title_hash` băm cả URL nên coi là hai bài.
- **Chép lại giữa các trang**: AgriS (SBT) vietstock ↔ cafef, containment 1,0, khác tiêu đề.
- **Cùng sự kiện, viết khác**: PNJ phát hành riêng lẻ 550 triệu cp (baodautu ↔ vietnambiz, 0,78); "HNX chuyển sang HOSE" (vietnambiz ↔ cafef, 0,47).
- **Bản cập nhật có tin mới**: PVcomBank "muốn bán giá cao hơn 60% thị giá" → "chốt giá 13.628 đồng/cp, cao hơn gần 40%". Cùng sự kiện nhưng có số liệu mới. Gộp mất bài sau là mất thông tin.
- **Chuyên mục định kỳ**: "Giá vàng sáng 28/9…" ↔ "…sáng 29/9", "Phân tích kỹ thuật phiên chiều 29/09" ↔ "30/09". Giống khuôn, khác nội dung, không bao giờ được gộp.
- **Dương tính giả do khuôn mẫu**: thông báo công bố thông tin của MBB, MSN, HCM, HDB trên cafef có containment 0,77–0,78 với nhau vì cùng văn mẫu.

SimHash hiện chỉ có ở 138/1.759 bài (8%). Các cặp có Hamming ≤ 10 phần lớn là hai bài không liên quan. SimHash 64 bit trên tin ngắn tiếng Việt không đủ phân giải để chống trùng giữa các bài.

### 2.4. Ước lượng khi mở rộng nguồn

Tỷ lệ trùng thật trên số bài cào được hiện vào khoảng 15–18%: 232 bài trùng thật hoặc gần trùng bị loại ở lớp cào, cộng 136 cụm thừa còn lọt. Tỷ lệ này tăng theo số nguồn cùng đưa một sự kiện, không tăng tuyến tính: tin công bố thông tin, giá vàng, vĩ mô, chính sách thường được 3–6 trang đưa cùng lúc. Với 20–30 nguồn, tỷ lệ 30–50% như kịch bản 500/1.000 là thực tế. Hạ tầng cần được dựng trước khi tới quy mô đó.

## 3. Phân loại trùng lặp và ai quyết định

| Loại                                | Định nghĩa                              | Ví dụ thật              | Phát hiện                                                                                | Quyết định  | Xử lý token                                          |
| ------------------------------------ | ------------------------------------------ | -------------------------- | ------------------------------------------------------------------------------------------ | -------------- | ------------------------------------------------------ |
| **T0 Bản sao kỹ thuật**     | cùng bài, khác URL hoặc khác bộ cào | cafef`?utm_source=`      | URL chuẩn hoá + SHA256 đoạn văn đã chuẩn hoá                                      | **code** | 0: bỏ hẳn bản sau, giữ URL làm bí danh           |
| **T1 Chép lại**              | trang khác đăng lại gần nguyên văn  | AgriS vietstock ↔ cafef   | containment ≥ 0,8**và** cùng tập số liệu, cùng tập mã CP                    | **code** | 0: kế thừa kết quả của bài gốc                  |
| **T2 Cùng sự kiện**         | viết lại, cùng sự thật                | PNJ 550 triệu cp          | code đề cử: containment 0,3–0,8, hoặc trùng mã CP + trùng số liệu, trong 48 giờ | **LLM**  | phân tích phần chênh                               |
| **T3 Cập nhật**              | cùng sự kiện, có sự thật mới        | PVcomBank 60% → 40%       | như T2                                                                                    | **LLM**  | phân tích phần chênh, gắn cờ "cập nhật"        |
| **T4 Chuyên mục định kỳ** | cùng khuôn, khác ngày, khác nội dung | "Giá vàng hôm nay 28/9" | khoá chuỗi chuyên mục (series key)                                                     | **code** | phân tích đầy đủ,**cấm gộp** khác ngày |

### Vì sao không dùng thuần LLM

- Chống trùng là so cặp. 1.000 bài là 500.000 cặp. LLM không thấy được cả kho trong một lượt. Muốn LLM quyết thì vẫn phải có code đề cử ứng viên trước.
- Đưa LLM đọc trọn 1.000 bài chỉ để biết bài nào trùng tốn gần bằng phân tích luôn 1.000 bài. Không tiết kiệm được gì.
- T0, T1, T4 có đáp án tất định. Giao cho LLM là thêm chi phí và thêm biến thiên cho việc vốn có lời giải chính xác.

### Vì sao không dùng thuần code

- T2 và T3 là ngữ nghĩa: "cùng sự thật hay có sự thật mới" không đo được bằng độ chồng chữ. PVcomBank 60% và 40% chồng chữ rất cao nhưng là hai tin khác nhau.
- Code ngưỡng cứng đã chứng minh sai: 46% loại nhầm ở lớp cào, GAS bị gộp với MWG.
- AGENTS.md §6.C cấm dùng heuristic để thay việc ngữ nghĩa của agent.

### Thực hành trong ngành

Các hệ tổng hợp tin lớn đều dùng mô hình lai: băm gần đúng (MinHash-LSH, SimHash) để chặn trùng cơ học ở quy mô lớn, chia khối (blocking) theo thực thể và cửa sổ thời gian để đề cử ứng viên cùng sự kiện, rồi dùng mô hình (embedding hoặc LLM) cho vùng xám. Với khối lượng 2.000–5.000 bài/ngày của dự án, chỉ mục ngược trên shingle hiếm là đủ, chưa cần vector DB hay dịch vụ embedding.

## 4. Kiến trúc đề xuất

```
Bronze (raw_html, bất biến)
   │
Silver (đoạn văn, SimHash)                         ← đã có
   │
[MỚI] story_cluster.py  (script, 0 token)
   ├─ T0: url_canonical + body_sha256              → gộp bí danh
   ├─ T4: series_key (khuôn tiêu đề + ngày)         → khoá, không gộp khác ngày
   ├─ chỉ mục shingle hiếm, cửa sổ 48 giờ
   ├─ T1: containment ≥ 0,8 + cùng số liệu + cùng mã CP  → member/copy
   └─ T2/T3: containment 0,3–0,8 hoặc cùng mã CP + số liệu → candidate (chờ LLM)
   │
   ▼  bảng story_clusters + cluster_members (vai trò, phương pháp, điểm, bằng chứng)
article_pack.py  — chọn theo vai trò
   ├─ canonical, đứng riêng, T4     → packet đầy đủ (như hiện nay)
   ├─ copy (T0/T1)                  → không vào packet
   └─ candidate (T2/T3)             → packet chênh: bản tóm tắt bài gốc + đoạn văn không chung
   │
wave_<mã>.conductor.ts — vẫn MỘT run_code
   ├─ Pha A: lô đầy đủ (song song)
   └─ Pha B: lô chênh, chèn bản tóm tắt từ đầu ra Pha A
   │
article_run.py --finish
   ├─ nạp đầu ra Pha A, B
   ├─ copy: ghi kết quả kế thừa (l1_source = 'inherited', trỏ về bài gốc)
   └─ độ phủ tính theo bài: phân tích + chênh + kế thừa
   │
write_user_output.py — một dòng mỗi câu chuyện, cột "Nguồn" liệt kê mọi trang, dòng cập nhật tách riêng
```

### 4.1. Lược đồ mới (Cấp 3)

```sql
CREATE TABLE story_clusters (
  cluster_id     TEXT PRIMARY KEY,
  canonical_id   TEXT NOT NULL,      -- url_title_hash của bài gốc
  first_seen_at  TEXT, last_seen_at TEXT,
  n_members      INTEGER, n_sources INTEGER
);
CREATE TABLE cluster_members (
  article_id   TEXT PRIMARY KEY,
  cluster_id   TEXT NOT NULL,
  role         TEXT NOT NULL,   -- canonical|alias|copy|candidate|same_event|update|series
  method       TEXT NOT NULL,   -- url|sha|shingle|llm
  score        REAL,
  evidence     TEXT,            -- JSON: shingle chung, số liệu chung, mã CP chung
  decided_by   TEXT,            -- code|<model>
  decided_at   TEXT
);
```

Thêm `url_canonical` cho `articles` (hoặc bảng bí danh riêng nếu không muốn đổi `UNIQUE(url)`).

### 4.2. Chế độ chênh của `article-processor` (Cấp 3, đổi hợp đồng)

Bài candidate nhận đầu vào rút gọn: bản tóm tắt và luận điểm của bài gốc (từ Pha A), cộng các đoạn văn của chính nó **không** chung shingle với bài gốc. Mô hình trả thêm:

- `same_event_as`: mã bài gốc, hoặc `null` nếu mô hình thấy là sự kiện khác (khi đó bài được tách cụm và xếp vào đợt sau, phân tích đầy đủ).
- `novelty`: `none | minor | new_facts`.
- Phần nhận diện thực thể và phân tích chỉ cho phần chênh, trích dẫn vẫn theo chỉ số đoạn của chính bài đó.

Quyết định và phân tích làm trong cùng một lượt, không thêm agent và không thêm bước. `story-dedup-clusterer` dạng draft chuyển sang `retired`: thiết kế cho lane Gold đã ngừng, và việc của nó đã nằm trong chế độ chênh.

### 4.3. Chốt chặn chống gộp nhầm (code)

Áp cho mọi quyết định T1 do code đưa ra:

- **Chốt số liệu**: tập các con số (số tiền, tỷ lệ, ngày, khối lượng) trong tiêu đề và đoạn đầu phải trùng nhau. Chặn PVcomBank 60% / 40%.
- **Chốt mã CP**: tập mã CP trong tiêu đề phải trùng nhau. Chặn GAS / MWG.
- **Chốt chuyên mục**: cùng `series_key` mà khác ngày thì không gộp.
- **Bỏ shingle khuôn mẫu** theo tần suất tài liệu trong từng domain. Chặn văn mẫu công bố thông tin.
- **Chốt tiêu đề hỏng**: tiêu đề dưới 8 ký tự hoặc chỉ có chữ số thì đưa vào dead-letter, không vào chỉ mục.

Bộ nhận diện theo danh mục (AGENTS.md §6.B) được dùng ở đây **chỉ để chia khối và chặn gộp**, không sinh kết quả nhận diện, không được tính là đã phân tích. Đúng phạm vi "đối chiếu để kiểm, không để thay".

### 4.4. Bất biến cần sửa (ADR 0016)

| Bất biến hiện tại                                    | Đề xuất                                                                                                                                                           |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "Mọi bài đều được xử lý đầy đủ."            | "Mọi**câu chuyện** được phân tích đầy đủ một lần. Mọi bài đều có kết quả: đầy đủ, chênh, hoặc kế thừa, kèm vai trò trong cụm." |
| Độ phủ đợt ≥ 90% ở cả hai lớp                   | Giữ ngưỡng. Mẫu số là số bài của đợt. Tử số gồm cả bài kế thừa và bài chênh đạt cổng DoD.                                                    |
| `l1_source = 'code_first'` bị loại khỏi phép đếm | Giữ nguyên. Thêm`l1_source = 'inherited'` được đếm, vì kết quả gốc do mô hình sinh ra.                                                               |

## 5. Lộ trình

### P0. Ngừng mất dữ liệu (Cấp 2, làm ngay, không cần ADR)

| #   | Việc                                                                                                                            | Proof                                                                      |
| --- | -------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 0.1 | Tắt loại bài theo khớp mờ ở lớp cào (`fuzzy_dedup: false` mặc định). Giữ khớp chính xác. Mọi bài vào Bronze. | test: hai tiêu đề`token_set` = 100, `ratio` < 60 đều được lưu |
| 0.2 | Chuẩn hoá URL: bỏ`utm_*`, `fbclid`, `gclid`, fragment. cafef khoá theo mã số cuối slug.                             | test: 9 cặp cafef thực tế ra cùng`url_canonical`                     |
| 0.3 | Chặn tiêu đề hỏng ở bộ cào baodautu, đưa vào dead-letter                                                              | test: tiêu đề`"1"` bị từ chối                                      |
| 0.4 | Chuẩn hoá`source_domain` trong `seen_articles` về tên miền                                                              | test                                                                       |
| 0.5 | Đưa script đo vào`scripts/dedup_audit.py` (chỉ đọc). Radar hiện một dòng tỷ lệ trùng theo T0–T4.                 | chạy trên ảnh chụp 3 ngày, ra đúng số trong §2                    |

Kỳ vọng: khoảng 200 bài mỗi 3 ngày không còn bị mất. Số bài vào Article Lane tăng khoảng 10%, đúng bằng phần trước đây bị loại nhầm.

### P1. Cụm hoá tất định, chỉ ghi nhận (Cấp 3: bảng mới)

`story_cluster.py` ghi `story_clusters` và `cluster_members` cho T0, T1, T4 và đánh dấu candidate T2/T3. **Chưa đổi** cách chọn bài của `article_pack`. Chạy song song 1–2 tuần để đo:

- tỷ lệ trùng thật theo từng loại và theo nguồn;
- độ chính xác của T1: lấy mẫu 100 cặp, `adversarial-dod-verifier` kiểm, mục tiêu gộp nhầm < 1%;
- tỷ lệ candidate T2/T3 so với tổng.

### P2. Cắt token ở T0/T1 (Cấp 3: đổi bất biến)

`article_pack` bỏ bài copy khỏi packet. `--finish` ghi kết quả kế thừa. Giao hàng gộp dòng theo cụm. Sổ cái token ghi thêm "token tránh được" để người dùng tự đối chiếu, không dùng làm cổng.

### P3. Chế độ chênh cho T2/T3 (Cấp 3: đổi hợp đồng `agent-output-v2-lean`)

Chương trình điều phối chạy Pha A rồi Pha B trong cùng một `run_code`. Hiệu chỉnh ngưỡng đề cử bằng một tập nhãn khoảng 200 cặp, lấy từ quyết định `same_event_as` của mô hình trong P3 và có người duyệt mẫu.

### P4. Tuỳ chọn, chỉ khi số đo đòi hỏi

Thêm embedding để tăng độ phủ T2 cho các bài viết lại ít chồng chữ. Chỉ làm khi P3 cho thấy mô hình thường xuyên báo `same_event_as` với các cặp mà code không đề cử.

## 6. Hiệu quả kỳ vọng

| Thời điểm         | Tỷ lệ trùng thật | Token tránh được                                                                                              |
| -------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Hiện tại, 8 nguồn | 15–18%              | P2: khoảng 4% (T0/T1). P3: thêm khoảng 3% (T2/T3 chỉ đọc phần chênh, ước tiết kiệm 60–70% mỗi bài) |
| 20–30 nguồn        | 30–50%              | 20–35%, phần lớn từ T1 (tin công bố thông tin, giá cả, vĩ mô được đăng lại)                      |

Ở quy mô hiện tại, giá trị lớn nhất của P0–P1 là **không mất bài và không gộp nhầm**. Tiết kiệm token trở thành giá trị chính khi số nguồn tăng.

## 7. Rủi ro

| Rủi ro                                             | Giảm thiểu                                                                                                                                                             |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Gộp nhầm làm mất tin                            | không xoá bài nào. Mọi quyết định có`evidence` và tách cụm được. Chốt số liệu và chốt mã CP. Kiểm mẫu bằng verifier.                           |
| Bài gốc phân tích lỗi kéo theo cả cụm       | chọn bài gốc theo độ dài nội dung và chất lượng nguồn, không theo thời điểm đăng. Bài gốc trượt DoD thì bài kế tiếp trong cụm lên làm gốc. |
| Cửa sổ 48 giờ cắt ngang sự kiện kéo dài     | cụm mở theo`last_seen_at`. Bài mới khớp cụm cũ thì vào làm candidate, không mở cụm mới.                                                                  |
| Pha B phụ thuộc Pha A, kéo dài thời gian đợt | Pha B chỉ chứa bài chênh, ngắn. Pha A thiếu bài gốc thì bài chênh được nâng thành bài đầy đủ.                                                       |
| Mở P0.1 làm tăng tải cào Bronze khoảng 20%    | trong khả năng hiện tại. Trùng T0 được chặn ngay ở URL chuẩn hoá trước khi tải trang.                                                                     |

## 8. Cụm trùng là tín hiệu: phải giữ gì

Để tín hiệu tần suất dùng được, cụm phải giữ đủ các trường sau. Đây là lý do không được gộp mất bài hay xoá bài:

| Trường giữ lại                                    | Tín hiệu sinh ra                                                                                                                                  |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| mọi thành viên,`source_domain`, `published_at` | **cường độ đưa tin**: số bài và số nguồn mỗi chủ đề mỗi ngày                                                                 |
| thứ tự đăng giữa các nguồn                     | **tốc độ lan truyền**: thời gian từ bài đầu tới bài thứ 3, nguồn nào đưa trước                                              |
| vai trò`copy` hay `same_event`                   | **tỷ lệ tin cũ đăng lại**: chủ đề được khuếch đại hay có diễn biến mới                                                     |
| vai trò`update` và `novelty`                    | **nhịp diễn biến**: một câu chuyện còn sinh tin mới hay đã bão hoà                                                                |
| sentiment của bài gốc và các bản chênh         | **sentiment theo câu chuyện** (mỗi câu chuyện một phiếu) tách khỏi **sentiment theo lượt đưa tin** (mỗi bài một phiếu) |

Kế thừa kết quả giúp các chỉ số này **đầy đủ hơn** hiện nay. Hiện chỉ 27% số bài từ 01/09 có kết quả mô hình (3.120/11.591). Khi bài trùng kế thừa thực thể và sentiment của bài gốc, phép đếm theo mã CP phủ được cả những bài chưa từng qua LLM.

## 9. Tầng thu thập không bỏ sót (thực thi ADR 0013)

### 9.1. Các điểm bỏ sót đang có

| Điểm                                                                                                  | Số đo                                                                                     | Loại                          |
| ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------ |
| Lọc mờ tiêu đề ở`base_scraper`                                                                  | 439 bài/3 ngày bị loại, 202 nhầm                                                       | bỏ chủ động                |
| Chỉ cào trang 1, chỉ 6 chuyên mục (baodautu)                                                       | kho có khoảng 50% số bài trong sitemap, đều mỗi ngày từ 20/09                      | bỏ do phạm vi                |
| Trang đầu cố định (cafef`PageSize: 20`, tnck `pages_per_cycle: 1`) cộng máy tắt 11–16 giờ | cafef sau mỗi lần nghỉ dài nạp dồn 51–103 bài, không có gì chứng minh đã đủ | bỏ do khoảng trống          |
| Dead-letter Silver                                                                                      | 1.461 tệp Bronze không tới được bước phân tích                                    | có raw nhưng mất ở xử lý |
| Tiêu đề hỏng (baodautu`"1"`)                                                                      | bài có, metadata sai                                                                      | sai dữ liệu                  |

### 9.2. Kiến trúc

```
Kênh phát hiện: listing, RSS, API, sitemap
        │
        ▼
discovered_urls  (sổ phát hiện, ghi TRƯỚC mọi bước lọc)
  url_canonical PK · source · first_seen_via · first_seen_at · state · attempts · last_error
  state ∈ discovered → captured | alias | gone | dead_letter    (không có "dropped")
        │
        ▼
Cào Bronze cho mọi URL ở trạng thái discovered     ← không lọc chủ đề, chuyên mục, độ giống
        │
        ▼
Silver → cụm trùng → Article Lane (bài trùng kế thừa kết quả)
```

Ba cơ chế bảo đảm độ đủ:

1. **Phân trang theo watermark.** Mỗi chu kỳ đọc listing tới khi gặp một trang toàn bài đã có trong `discovered_urls`, có trần an toàn số trang theo nguồn. Máy chạy lại sau khi tắt thì tự đọc sâu hơn cho tới khi chạm watermark.
2. **Đối chiếu sitemap hằng ngày** (`scripts/capture_reconcile.py`, 0 token). Sitemap, news sitemap hoặc API theo ngày được dùng làm nguồn đối chiếu độc lập. URL có trong sitemap mà chưa có trong `discovered_urls` thì được ghi với `first_seen_via = 'reconcile'` và cào bù. Số URL vào kho qua đường này đo đúng độ hụt của kênh chính.
3. **Thước đo độ phủ thu thập trên radar.** Mỗi nguồn mỗi ngày: số bài sitemap báo, số bài đã có, số bài thiếu, số bài vào qua cào bù. Thiếu > 2% là ĐỎ.

### 9.3. Thứ tự làm

| #  | Việc                                                                                                                           | Cấp            |
| -- | ------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| C1 | P0.1–P0.4 ở §5 (tắt lọc mờ, chuẩn hoá URL, chặn tiêu đề hỏng, chuẩn hoá domain)                                  | 2               |
| C2 | `capture_reconcile.py` chỉ đọc cho baodautu và cafef, in độ hụt theo ngày. Đưa lên radar.                          | 2               |
| C3 | Bảng`discovered_urls` và vòng đời trạng thái. Bộ cào ghi sổ trước khi lọc.                                       | 3 (lược đồ) |
| C4 | Phân trang theo watermark cho mọi bộ cào listing. Bỏ giới hạn chuyên mục khỏi phạm vi, chỉ giữ để xếp thứ tự. | 2               |
| C5 | Cào bù tự động từ kết quả đối chiếu. Xử lý dứt điểm 1.461 dead-letter Silver.                                   | 2               |
