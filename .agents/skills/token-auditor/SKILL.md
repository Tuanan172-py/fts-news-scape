---
name: token-auditor
description: Chuyên viên kiểm toán ngân sách LLM, đo lường lượng token burn thực tế, tối ưu cắt tỉa payload và cảnh báo vượt hạn mức (Human-in-the-loop).
---

# Token Auditor & Payload Pruner Agent Skill

> **Mục tiêu cốt lõi:** Giữ cho toàn bộ luồng thực thi luôn "Lean & Clean", triệt tiêu hoàn toàn rác ngữ cảnh, kiểm soát chi phí LLM ở mức thấp nhất và ngăn chặn hiện tượng quá tải token.

---

## 1. Định Hướng & Bất Biến Nghiệp Vụ (Context & Domain Invariants)

1. **Định Mức Thực Nghiệm (Empirical Benchmark — Model Flash)**:
   - **Tầng L1**: ~450 tokens / bài (~350 input + 100 output).
   - **Tầng Gold (v2-lean)**: ~1.470 tokens / bài (~860 input + 610 output).
   - Chi phí ước tính: ~$0.15 USD / 1 triệu tokens (Flash).
2. **Bất Biến Phễu Lọc Subscriber-Gating (ADR 0005)**:
   - Chỉ xuất task phân tích Gold cho các bài viết có thực thể nằm trong Watchlist của người dùng đang active.
   - Các bài không có người đăng ký BẮT BUỘC lưu trữ ở trạng thái `L1_ONLY` trong database.
   - Tỷ lệ cắt giảm token vô ích kỳ vọng: **$\ge 85\% - 91\%$**.
3. **Quy Chuẩn Cắt Tỉa Payload Tinh Gọn (Dynamic 3-Pass Pruner)**:
   - **Zero-Waste Task Packet**: Tuyệt đối loại bỏ `structure.links` (hàng ngàn link menu/footer), `structure.headings` và `images`. Dung lượng 1 packet $< 10$ KB.
   - **Dynamic 3-Pass Semantic Pruning (2.200 Chars Max)**: Trần ký tự bài viết tối đa 2.200 chars. Cắt tỉa theo nguyên khối đoạn văn `<p>` (giữ 2 đoạn Sapo $\rightarrow$ đoạn chứa Ticker L1 $\rightarrow$ số liệu tài chính), tuyệt đối không cắt vụn câu chữ để bảo toàn Grounded Citations.
4. **Kiến Trúc Phễu Lọc 4 Tầng & Quy Chuẩn Kích Thước Batch**:
   - **Tầng 1 (Code-First Title Matcher)**: 0 token, giải quyết ~60% bài cào.
   - **Tầng 2 (L1 Mini-Batch Waves)**: Cố định 25 bài/batch, 2–3 batches/đợt (~25.000 tokens/đợt).
   - **Tầng 3 (Subscriber-Gating)**: Lọc qua Watchlist, loại bỏ 85%–91% bài vô bổ.
   - **Tầng 4 (Gold Pruned Mini-Batches)**: Cố định 5 bài/batch, Dynamic 3-Pass Pruning <= 2.200 chars.
5. **Chiến Lược 3 Waves Cho Tầng Gold**:
   - Wave 1: Nhóm Cổ phiếu trọng tâm (VIC, VHM, HPG, FPT, TCB, MBB...) (10–15 bài).
   - Wave 2: Vĩ mô & Ngành kinh tế (Tỷ giá, Lãi suất, Bất động sản...) (15–20 bài).
   - Wave 3: Hoàn tất backlog còn lại trước 16:30.
6. **Hạn Mức An Toàn (Safety Token Cap)**:
   - Tốc độ sinh: <= 100.000 tokens/phút.
   - Trần ngân sách ngày: <= 350.000 tokens (~$0.05 USD).

---

## 2. Quy Trình Vận Hành & Đo Lường (Auditing Workflow)

```
[Mỗi Chu Kỳ Vận Hành Hoặc Cuối Ngày]
       │
       ▼
[Bước 1: Tính Toán Token Burn Thực Tế]
  ├── Đếm số bài L1 chạy qua Subagents vs Code-First (0 token)
  ├── Đếm số bài Gold chạy qua Subagents Flash
  └── Tính toán tổng lượng token tiêu thụ và chi phí USD tương ứng
       │
       ▼
[Bước 2: Đo Lường Hiệu Quả Bộ Lọc Gating]
  ├── Tỷ lệ chọn lọc Gold = (Số bài Gold / Tổng bài L1) * 100%
  └── Tỷ lệ token tiết kiệm = 100% - Tỷ lệ chọn lọc Gold
       │
       ▼
[Bước 3: Cảnh Báo Bất Thường (Cost & Token Drift Alert)]
  ├── Nếu tỷ lệ chọn lọc Gold > 25% -> Kiểm tra xem Watchlist có chứa từ khóa quá rộng không
  └── Nếu dung lượng task packet > 20 KB -> Kiểm tra bộ lọc pruner.py có bị bypass không
```

---

## 3. Bộ Công Cụ Cơ Học Thực Thi (Execution Tooling)

```powershell
# 1. Đo lường mức tiêu thụ token và tỷ lệ tiết kiệm hôm nay:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token

# 2. Đo lường cho một ngày cụ thể:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token --date YYYY-MM-DD
```

---

## 4. Báo Cáo Đo Lường Mẫu (Canonical Token Report)

```text
================================================================================
 🪙  NEWS-SCAPE TOKEN METRICS & BUDGET AUDITOR — [2026-09-14]
================================================================================
1. THỰC NGHIỆM TIÊU THỤ TOKEN (TIÊU CHUẨN FLASH / LEAN SCHEMA):
   • Tầng L1 (Subagents) : 408 bài × ~450 tokens = ~183,600 tokens
   • Tầng L1 (Code-First): 356 bài (TIẾT KIỆM 100%) = ~160,200 tokens tiết kiệm
   • Tầng Gold (Subagents): 64 bài × ~1470 tokens = ~94,080 tokens
   ────────────────────────────────────────────────────────────────────────
   🔥 TỔNG TOKEN TIÊU THỤ THỰC TẾ  : ~277,680 tokens (~0.278M tokens)
   💡 TỔNG TOKEN ĐÃ TIẾT KIỆM ĐƯỢC : ~1,189,200 tokens

2. ĐÁNH GIÁ HIỆU QUẢ SUBSCRIBER-GATING & CLEAN SCHEMA:
   • Tỷ lệ chọn lọc Gold qua Watchlist : 8.4% (64/764 bài)
   • Tỷ lệ cắt giảm Token vô ích       : 91.6% chi phí tránh lãng phí
   • Chi phí ước tính (Google Flash)    : ~$0.0417 USD (Cực kỳ tối ưu)
================================================================================
```
