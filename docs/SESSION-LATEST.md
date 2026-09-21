# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-18 (Article Lane — triển khai trọn bộ, chưa chạy workload thật)
- **Điểm vào:** `plans/20260918-1651-article-lane-unified/plan.md` là **tài liệu quy phạm duy nhất**
- **Vận hành:** `.agents/dsh/RUNBOOK-article-lane.md`
- **Bối cảnh lớp code-first:** `docs/CODE-FIRST-LANDSCAPE.md` (lập 2026-09-21) — bản đồ codebase, số đo thật, 5 nhóm vấn đề, 8 hướng dư địa; đọc trước khi phát triển tiếp tầng nhận diện tất định

## Đã làm trong phiên này

Gộp hai tầng L1 và Gold thành **một agent, một bước cho cả lô**. Ba vòng audit trước đó cho ra ba plan; phiên này hợp nhất chúng thành một, chốt sáu quyết định, rồi triển khai toàn bộ.

**Vá bốn khiếm khuyết P0 đang sống** (xác minh trực tiếp trong mã nguồn DSH, không suy đoán):

| # | Sự thật | Hệ quả đã xảy ra |
|:-:|---|---|
| P0-1 | `maxDepth: 0` **cấm delegation hoàn toàn**, không phải chặn đệ quy | `agent_l1` và `agent_gold` **chưa bao giờ spawn được** kể từ khi preset ra đời |
| P0-2 | `run_code` được chèn **sau** lớp lọc `toolFilter`, và `restrict()` ném lỗi nếu cố đặt tên nó | Con PTC không bao giờ đạt "0 tool"; tiêu chí đúng là SDK rỗng và `turns == 1` |
| P0-3 | Row subagent có đúng 9 khoá, **không có `mode`** | Không thể cho con chạy `native`; Conductor buộc giữ `ptc` |
| P0-4 | Bộ cắt kết quả công cụ **không đăng ký listener nào** | Không có gì cắt ngữ cảnh trước ngưỡng nén 80% |

**Mã mới** — tất cả 0 token: `article_run.py` (gộp cả đợt vào một lệnh), `article_pack.py`, `article_expand.py`, `build_article_prefix.py`, `token_ledger.py`, `estimate_wave.py`, `ctx_probe.py`, `handoff.py`, `src/telemetry/dsh_usage.py`, `src/agent/distill.py`, `src/agent/intent_resolve.py`.

**Bằng chứng đã đo, không phải ước lượng:**

| Hạng mục | Kết quả |
|---|---|
| Sáu luật kế toán token | Đối soát trên phiên thật, **đều đạt** |
| Chắt lọc đoạn trên 200 bài thật | **0 lỗi nguyên văn**, trung bình 786 token/bài từ 1.414 |
| Cổng nghiệm thu L1 trên 100 bài | **100/100 đạt** |
| Trích dẫn theo chỉ số đoạn | **0 lỗi**, đúng nguyên văn do cấu trúc |
| Cứu bản ghi khi đầu ra hỏng | 100 bản ghi cứu được dù phần tử cuối cố tình hỏng |
| Ngữ cảnh đỉnh, lô 100 bài | **12,3%** của cửa sổ, khớp dự đoán 12,2% |
| Bộ kiểm định | 32 test mới cho Article Lane |

**Đính chính một chỗ plan nói sai:** quy tắc "bắt buộc compact JSON" suy diễn sai chiều. Giới hạn thật của công cụ đọc là 2.000 ký tự **mỗi dòng** và 51.200 byte **mỗi lần gọi**, nên compact dồn cả packet vào một dòng 267 nghìn ký tự sẽ mất 99,3% nội dung. Quy tắc đúng là **không dòng nào vượt trần**, đạt được bằng cách tách nội dung thành mảng đoạn rồi ghi xuống dòng theo phần tử. Đoạn dài nhất đo trên 4.493 đoạn thật chỉ 954 ký tự.

## Dọn dẹp đã làm

Quá trình kiểm chuỗi có nạp dữ liệu mô phỏng vào cơ sở dữ liệu vận hành. **Đã dọn sạch**: 214 bản ghi nhận diện, 220 bản ghi nội dung, 5 tệp Excel và các mục checkpoint tương ứng. Sao lưu cơ sở dữ liệu trước khi xoá tại `C:/data/news-scape/monocle.db.bak-20260918T172336`. Đã xác nhận không còn dấu vết.

## Next Steps

1. **Dán prefix vào preset.** Chép trọn `project/data/prefix/ARTICLE_SYSTEM_CORE.md` vào trường `persona` của row `tool-subagent-article`. Đây là việc thủ công duy nhất còn lại.
2. **Chạy thử một đợt nhỏ** trên DSH, ví dụ `--limit 100 --batch 50`, rồi đọc `estimate_wave.py --wave <mã>` để xem sai số dự toán.
3. **Canh bốn dấu hiệu** ở §2 của runbook: `turns_max`, `reasoning`, token mỗi bài, áp suất ngữ cảnh.
4. Sau một chu kỳ chạy sạch mới dọn đường cũ và mở chiến dịch backlog **2.118 bài**.

## Việc còn treo

- `leaders.yaml` cho nhóm tên người chưa có. Nhóm này hiện luôn rơi vào ngoài danh mục, **đúng thiết kế**: giai đoạn đầu nó là cơ chế thu thập dữ liệu, không phải cơ chế nhận diện. Đo bằng số tên thu được, không đo bằng tỷ lệ tra cứu.
- Amendment ADR 0008 gỡ cổng xác nhận: đã soạn nội dung trong plan §8, chưa ghi vào tệp ADR.
