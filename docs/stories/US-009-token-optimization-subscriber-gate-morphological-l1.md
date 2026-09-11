# Story US-009: Tối Ưu Hóa Token Burn Toàn Hệ Thống & Triệt Tiêu Sai Lệch Thực Thể L1

- **ID**: US-009
- **Phân loại rủi ro**: Cấp 2 (NORMAL)
- **Trạng thái**: `implemented`
- **Chủ đề**: Subscriber-Gated Gold Export, Morphological Capitalized Suffix Guard, 3-Pass Semantic Pruner, L1 Missed-Only Routing
- **Liên kết**: [ADR 0005](../decisions/0005-subscriber-gated-gold-va-morphological-l1-guard.md), US-007, US-008

---

## 1. Bối cảnh & Vấn đề

- **Rò rỉ token tầng Gold**: `agent_export.py` bốc mọi bài có L1 mà không quan tâm bài viết có người dùng active nào đăng ký hay không. Trên thực tế đo được 483/1.274 bài (~38%) chạy Gold lãng phí token vì không ai nhận.
- **Bẫy danh từ riêng ghép tiếng Việt ở L1**: Từ đơn có dấu như `"Mỹ"` bị regex `\bMỹ\b` bắt trúng các địa danh ghép (*"Mỹ Thuận"*, *"Mỹ Tho"*, *"Mỹ Thủy"*), tên người (*"Phạm Thị Mỹ Diệu"*), thương hiệu (*"Á Mỹ Grupo"*), gán nhầm sang `MACRO_GEO:MY`.
- **Trần ký tự pruner cũ**: 4.000 ký tự gây phình input token không cần thiết; duyệt tuần tự break sớm có thể bỏ sót đoạn văn chứa mã CP ở cuối bài.
- **Định tuyến L1 cũ**: Mặc định `--review all` khiến LLM phải duyệt lại 62% bài đã được code-first giải quyết xong.

---

## 2. Giải pháp Đã Triển Khai

1. **Morphological & Prefix Guard (`src/agent/entities.py`)**:
   - `Capitalized Suffix Guard`: Chặn alias *"Mỹ"* nếu từ liền sau viết hoa mà không nằm trong `_INTL_AFTER_MY` (`Trump`, `Biden`, `Fed`, `Wall Street`...).
   - `Prefix Guard`: Chặn nếu từ liền trước là tiền tố thương hiệu (`Á`, `Phú`, `Phù`) hoặc danh xưng (`Bà`, `Ông`, `Thị`).
   - Tinh chỉnh `_context_guards.yaml` loại bỏ các từ ghép dễ đè từ thường khi fold (`my lam` đè `Mỹ làm`).
2. **Cổng Chặn Subscriber-Gated Export (`src/handoff/catalog.py`, `src/agent/runner.py`, `scripts/agent_export.py`)**:
   - Thêm `allowed_article_ids` vào `Catalog.claim` sử dụng SQLite temp table `_allowed_aids`.
   - `AgentRunner.export_tasks` thêm cờ `subscriber_only=True` (mặc định BẬT), chỉ bốc các bài viết có `l1_entities` nằm trong Watchlist của người dùng đang active (`manifest.yaml`).
   - `agent_export.py` bổ sung cờ `--subscriber-only` / `--no-subscriber-only`.
3. **Semantic Pruner 3-Pass (`src/agent/pruner.py`, `src/agent/packet.py`)**:
   - Hạ trần mặc định từ `4.000` xuống `2.200` ký tự.
   - Thuật toán 3-pass: Giữ tối đa 2 đoạn đầu (Sapo) $\rightarrow$ Ưu tiên quét đoạn chứa mã CP từ `l1_entities` / từ khóa tài chính $\rightarrow$ Điền đầy theo thứ tự gốc.
   - `build_gold_input` trong `packet.py` truyền `l1_entities` vào pruner.
4. **Tối ưu Định tuyến L1 (`scripts/l1_route.py`, `scripts/run_agent_hierarchy.py`)**:
   - Đổi mặc định `--review` thành `missed`.
   - `run_agent_hierarchy.py` gọi `l1_route.py --review missed` và `agent_export.py --subscriber-only`.

---

## 3. Bằng Chứng Kiểm Thử (Verification Proof)

- Unit test toàn bộ các module liên quan: `pytest tests/test_entities.py tests/test_pruner_and_batch.py tests/test_l1_router.py tests/test_user_output.py -v` $\rightarrow$ **37/37 passed (100% green)**.
- Kiểm thử thực tế trên 7.656 bài trong `monocle.db`:
  - 100% false positive `MACRO_GEO:MY` (Mỹ Thuận, Á Mỹ, Mỹ Diệu, Mỹ Thủy, Mỹ Lâm...) giảm về 0.
  - 300 bài viết vĩ mô Mỹ thực sự được bảo toàn 100%.
- Kiểm thử phễu subscriber: 947 / 1505 bài L1 được chọn, loại bỏ 558 bài không ai xem (tiết kiệm 37.1% token Gold).
