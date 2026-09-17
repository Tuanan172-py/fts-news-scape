# Thiết kế — Kiến trúc Quy trình Medallion: Bronze, Silver, Gold

Cập nhật: 2026-09-17 · Tác giả: Antigravity 2.0 · Trạng thái: ACTIVE.
Tài liệu hóa chi tiết workflow 3 tầng Medallion theo định dạng trực quan (ASCII execution flow) từ cào dữ liệu gốc đến phân tích chuyên sâu và giao hàng.

---

## 1. Tầng Bronze: Thu thập & Lưu trữ Nguyên bản (Raw WORM Ingestion)

Tầng Bronze chịu trách nhiệm cào dữ liệu thô, lọc trùng cơ bản và lưu trữ nguyên bản bất biến (WORM - Write Once, Read Many). Mọi dữ liệu Bronze là nguồn chân lý (Single Source of Truth) để tái sinh các tầng sau.

```text
[BẮT ĐẦU: CÓ URL RSS FEED / DOMAIN ENTRYPOINT]
       │
       ▼
 1. [ feedparser ] 
    - Gửi 1 HTTP request đến link RSS.
    - Parse dữ liệu XML nguồn.
       │
       ▼
 2. [ parse_item() ]
    - Xử lý trên RAM (thuần CPU, rất nhẹ).
    - Map dữ liệu thô thành đối tượng `Article`.
       │
       ▼
 3. [ Dedup (Lọc trùng lặp) ]
    - Băm SHA256(url + title) tra cứu trong bảng `seen_articles`.
    - Dùng `rapidfuzz` so sánh fuzzy title (cửa sổ 48h, ngưỡng similarity 90).
       │
       ├────────────────────────────────┐
       │ (TRÙNG LẶP)                    │ (BÀI MỚI)
       ▼                                ▼
  [ BỎ QUA ]                      4. [ enrich() ] Gọi _capture_and_extract()
                                        │
                                        ▼
                                  5. [ RobotsGate ]
                                     - Kiểm tra file robots.txt của domain.
                                     - Sử dụng cache 24h để tối ưu.
                                        │
                                        ▼
                                  6. [ SourceBackoff.before_fetch ]
                                     - Kiểm soát tần suất gửi request (Rate limiting).
                                     - Tránh đánh sập server nguồn.
                                        │
                                        ▼
                                  7. [ http.get_response ]
                                     - Dùng HTTP GET thuần (như thư viện requests).
                                     - Trả về mã nguồn HTML tĩnh.
                                        │
                                        ▼
                                  8. [ RawStore.save() ]
                                     - Ghi trực tiếp html (byte-exact) xuống ổ cứng (`data/raw_html/`).
                                     - Lưu kèm metadata `.meta.json` (SHA256, fetch_ts, headers).
                                     - Phục vụ lưu trữ gốc/truy xuất lại bất biến.
                                        │
                                        ▼
                                  9. [ Phân tích Cú pháp (Extraction) ]
                                     Dùng: BeautifulSoup(html, "lxml").select_one(selector)
                                        │
                                        ├────────────────────────────────┐
                                        │ (TÌM THẤY SELECTOR)            │ (SAI/LỆCH SELECTOR)
                                        ▼                                ▼
                                 [ LƯU DỮ LIỆU ]                10. [ _density_extract() ] (FALLBACK)
                                 (Nhanh, nhẹ CPU)                   - Phân tích mật độ văn bản.
                                                                    - Dùng thư viện: readability-lxml + goose3.
                                                                    - (Tốn nhiều CPU hơn do quét toàn trang).
                                                                         │
                                                                         ▼
                                                                    [ LƯU DỮ LIỆU ]

[KẾT THÚC BRONZE: DỮ LIỆU LƯU TRỮ TẠI data/raw_html/ VÀ articles TABLE]
```

---

## 2. Tầng Silver: Tinh lọc Đoạn văn & Đóng gói Handoff (0 Token • Lean Payload)

Tầng Silver đóng vai trò cầu nối thuần deterministic (0 token LLM), làm sạch rác DOM, phát hiện biến đổi nội dung qua SimHash và tinh lọc payload thành các khối đoạn văn `<p>` sạch sẽ.

```text
[BẮT ĐẦU: DỮ LIỆU BRONZE (raw_html + .meta.json)]
       │
       ▼
 1. [ DOM Normalization & Boilerplate Stripping (pruner.py) ]
    - Bóc tách nội dung theo từng nguyên khối đoạn văn (<p>).
    - Cắt bỏ 100% rác DOM: header, footer, menu, widget, quảng cáo, copyright, bài liên quan.
    - Loại bỏ triệt để `structure.links` (hàng ngàn link menu) và `images` (giảm dung lượng < 10 KB).
       │
       ▼
 2. [ Change Detection & SimHash (change_detect.py) ]
    - Tính mã băm SimHash 64-bit trên tập từ vựng văn bản.
    - So sánh Hamming distance và DOM Signature với phiên bản trước trong `article_versions`.
    - Phân loại: NEW, UNCHANGED, CONTENT_CHANGED, TEMPLATE_DRIFT, SELECTOR_BROKEN.
       │
       ▼
 3. [ Dynamic 3-Pass Semantic Pruning (Trần tối đa 2.200 ký tự) ]
    - Pass 1: Giữ tối đa 2 đoạn đầu tiên (Sapo / phần mở đầu tóm tắt).
    - Pass 2: Quét ưu tiên các đoạn chứa mã cổ phiếu, chỉ số hoặc số liệu tài chính quan trọng.
    - Pass 3: Điền đầy các đoạn văn theo thứ tự ban đầu cho đến khi chạm trần 2.200 ký tự.
    - RÀNG BUỘC BẢO TOÀN NGUYÊN BẢN: Giữ nguyên khối văn bản của từng `<p>`, không cắt tỉa câu chữ
      (bảo đảm exact substring cho trích dẫn citations >= 20 ký tự ở tầng Gold).
       │
       ▼
 4. [ L1 Code-First Entity Screening (l1_route.py) ]
    - Áp dụng bộ lọc hình thái học (Morphological Guard: Capitalized Suffix Guard, Prefix Guard).
    - Triệt tiêu 100% false-positive địa danh, danh xưng mà không tốn token LLM.
       │
       ├────────────────────────────────┐
       │ (ĐÃ KHỚP CHÍNH XÁC CODE-FIRST)  │ (MƠ HỒ / BÀI CHƯA RÕ THỰC THỂ)
       ▼                                ▼
 5a. [ l1_ingest.py --code-first ]     5b. [ Đóng gói L1 Task Packet ]
     - Ghi nhận thực thể vào DB (0 token). - Lưu vào `data/agent_tasks/l1/<id>.task.json`.
     - Sẵn sàng chuyển tiếp sang Gold.    - Chờ L1 Subagent xử lý semantic.
       │                                │
       └────────────────────────────────┘
                                        │
                                        ▼
 6. [ Task Packaging & Mini-Batching ]
    - Gom lô 5–10 bài vào `data/agent_tasks/batch_XX.task.json`.
    - Nhúng `input.l1_entities` có sẵn để tiếp sức cho Agent Gold (quy tắc 2-I/O).
       │
       ▼
[KẾT THÚC SILVER: GÓI CÔNG VIỆC SẴN SÀNG CHUYỂN GIAO CHO AGENT]
```

---

## 3. Tầng Gold: Xử lý Ngữ nghĩa Đa tầng & Giao hàng Người dùng (Agent Intelligence & Delivery)

Tầng Gold là vùng trí tuệ nhân tạo (Subagents LLM) đảm nhận bóc tách thực thể sâu, tóm tắt, chấm điểm trọng yếu, trích dẫn chứng cứ và phân phối báo cáo theo Watchlist người dùng.

```text
[BẮT ĐẦU: MINI-BATCH TASK PACKET (data/agent_tasks/batch_XX.task.json)]
       │
       ▼
 1. [ Subscriber-Gated Filter (ADR 0005) ]
    - Đối chiếu `l1_entities` với Watchlist người dùng active trong `manifest.yaml` (vd: AnPT).
       │
       ├────────────────────────────────┐
       │ (KHÔNG CÓ NGƯỜI ĐĂNG KÝ)       │ (KHỚP WATCHLIST NGƯỜI DÙNG)
       ▼                                ▼
  [ LƯU TRẠNG THÁI L1_ONLY ]        2. [ invoke_subagent: Gold Financial Analyst ]
  (Tiết kiệm 38%–45% token)            - Model: Flash/Pro với System Prompt chuyên trách.
                                       - Tuân thủ quy tắc 2-I/O:
                                         • 1 lần `view_file` nạp toàn bộ mini-batch.
                                         • 1 lần `write_to_file` xuất mảng kết quả JSON.
                                       - Chuẩn dữ liệu `agent-output-v2-lean`:
                                         • `summary`: diễn giải độc lập súc tích.
                                         • `key_points`: lập luận tài chính riêng (KHÔNG sao chép citations).
                                         • `implication`: tác động doanh nghiệp / dòng tiền / cổ phiếu.
                                         • `sentiment`: positive / negative / neutral.
                                         • `materiality_score`: thang số thực 0.1 – 1.0.
                                         • `citations`: >= 2 chuỗi con nguyên bản exact substring (>= 20 ký tự).
                                          │
                                          ▼
                                    3. [ Quality Gating & DoD Verification (dod-gatekeeper) ]
                                       - Kiểm tra schema JSON v2-lean hợp lệ.
                                       - Kiểm tra trích dẫn nguyên văn: Mọi chuỗi trong `citations`
                                         phải tồn tại chính xác từng ký tự trong `cleaned_text`.
                                       - Kiểm tra chống đạo văn: Từ chối nếu `key_points` trùng lặp với `citations`.
                                          │
                                          ├────────────────────────────────┐
                                          │ (ĐẠT 100% CHUẨN DoD)           │ (VI PHẠM QUY TẮC)
                                          ▼                                ▼
                                    4. [ DBWriter: Agent Ingest ]    [ TỪ CHỐI NẠP DB ]
                                       - Transaction `BEGIN IMMEDIATE`. - Đánh dấu `failed` / ghi log.
                                       - Tự động điền metadata kỹ thuật  - Cơ chế tự học và sửa prompt.
                                         (zero-token metadata).
                                       - Ghi nhận KPI vào `harness.db`.
                                          │
                                          ▼
                                    5. [ User Workflow Delivery (user_output.py) ]
                                       - Phân tuyến dữ liệu theo Watchlist từng user.
                                       - Smart Idempotency Skip: Bỏ qua ghi đè nếu file không đổi.
                                       - Byte-level Equality Guard: Triệt tiêu xung đột sync OneDrive.
                                       - Xuất báo cáo Excel: `users/output/<user>/<date>.xlsx`.
                                          │
                                          ▼
                               [KẾT THÚC GOLD: HOÀN TẤT PHÂN PHỐI CHO NGƯỜI DÙNG]
```

---

## 4. Tóm tắt Ma trận Phân tầng (Medallion Summary Matrix)

| Đặc tính | Bronze | Silver | Gold |
| :--- | :--- | :--- | :--- |
| **Bản chất** | Raw WORM (Bất biến) | Deterministic Clean (0 token) | AI Cognitive Intelligence |
| **Định dạng lưu trữ** | `.html` + `.meta.json` (`data/raw_html/`) | `.json` (`data/silver/`) & `batch_XX.task.json` | `data/agent_outputs/` & SQLite `monocle.db` |
| **Token LLM tiêu thụ** | 0 token | 0 token | ~1.770 token / bài (Flash) |
| **Ràng buộc cốt lõi** | Byte-exact SHA256, WORM | Dynamic 3-Pass $\le 2.200$ chars, nguyên khối `<p>` | Exact substring $\ge 20$ chars, 2-I/O boundary |
| **Cơ chế kiểm định** | Schema 14 keys, SHA256 checksum | SimHash 64-bit, DOM path signature | Cổng DoD Gatekeeper v2-lean |
| **Đầu ra chính** | Kho HTML nguyên bản | Gói nhiệm vụ Mini-batch | Deliverable Excel (`users/output/`) |
