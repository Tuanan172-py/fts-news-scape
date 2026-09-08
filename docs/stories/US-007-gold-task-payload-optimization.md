# Story US-007: Tối ưu hóa Context & Handoff Subagents Gold (Payload Pruning, L1 Enrichment & Batch Handoff)

- **ID**: US-007
- **Phân loại rủi ro**: Cấp 2 (NORMAL)
- **Trạng thái**: `implemented`
- **Chủ đề**: Task Packet Payload Compression, Verbatim Paragraph Pruning, L1-Assisted Triage & Consolidated Batch Handoff

## 1. Bối cảnh & Vấn đề

- Nút thắt cổ chai ở tầng Gold (Agents Realm): Task packet đơn lẻ `04019f860...task.json` nặng tới 182 KB (chứa hàng ngàn menu links và image URLs từ DOM), khiến LLM bị ngốn cạn token input, chậm I/O và dễ suy giảm khả năng chú ý (attention degradation).
- Lô 50 bài cần 100 tool calls tuần tự, gây lãng phí lớn.
- Khâu bóc tách `cleaned_text` đôi khi còn sót lại boilerplate chân trang tòa soạn, thông tin hotline, teaser bài liên quan.
- Kết quả L1 chưa được tận dụng để tiếp sức cho Gold.

## 2. Giải pháp Triển khai

1. **Paragraph Pruner (`src/agent/pruner.py`)**:
   - Loại bỏ triệt để các đoạn văn rác (teaser "Bài liên quan", thông tin tòa soạn, hotline, email, copyright, nguồn vặt).
   - Áp dụng nguyên lý Inverted Pyramid với trần ký tự (4.000 chars), bảo toàn 100% nguyên văn các đoạn văn để đảm bảo trích dẫn `citations` khớp chính xác từng ký tự trong `cleaned_text`.
2. **Zero-Waste Task Packet (`src/agent/packet.py`)**:
   - `build_gold_input()`: Loại bỏ 100% `structure.links` và `images`, chỉ giữ các trường cốt lõi. Giảm dung lượng file task từ 182 KB xuống 6–8 KB (giảm 96%).
3. **Consolidated Mini-Batch Handoff (`src/agent/batch_handoff.py`)**:
   - Gom 5–10 bài vào 1 batch packet `batch_XX.task.json`.
   - `unpack_batch_output()` giải nén linh hoạt các định dạng batch output để nạp database.
   - Giảm 90% số lượng tool calls cho Subagents (từ 20 calls/10 bài xuống còn 2 calls).
4. **L1 Metadata Enrichment (`src/agent/runner.py`)**:
   - Tự động nạp mã CP từ `l1_outputs` vào trường `input.l1_entities` của Gold task.
5. **Cập nhật Scripts & Subagent Skill**:
   - Bổ sung `--mini-batch` vào `agent_export.py` và `run_agent_hierarchy.py`.
   - Cập nhật `.agents/skills/gold-financial-analyst/SKILL.md` hướng dẫn chế độ Batch Mode.
   - Sửa lỗi phụ trợ `_is_owner_alive()` trong `src/db/store.py` cho opaque identifiers.

## 3. Bằng chứng Kiểm thử (Verification Proof)

- Unit test: `tests/test_pruner_and_batch.py` (6 tests passed).
- Test suite toàn dự án: 263 passed, 0 failed.
- Benchmark thực tế: Kích thước task packet giảm 96%, batch packet 5 bài chỉ ~25 KB.
