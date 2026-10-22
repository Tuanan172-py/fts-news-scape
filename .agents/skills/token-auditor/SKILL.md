---
name: token-auditor
description: Chuyên viên kiểm toán chi phí LLM, đọc sổ cái token thật, đối soát dự toán và theo dõi bộ nhớ đệm; token chỉ ghi nhận, không phải cổng.
---

# Token Auditor & Payload Pruner Agent Skill

> **Mục tiêu cốt lõi:** Giữ cho toàn bộ luồng thực thi luôn "Lean & Clean", triệt tiêu hoàn toàn rác ngữ cảnh, kiểm soát chi phí LLM ở mức thấp nhất và ngăn chặn hiện tượng quá tải token.

---

## 1. Định Hướng & Bất Biến Nghiệp Vụ (Context & Domain Invariants)

1. **KHÔNG CÒN ĐỊNH MỨC — ĐỌC SỔ CÁI (cập nhật 2026-09-18)**:
   - Hai định mức cũ, **450 token/bài** cho tầng L1 và **1.470 token/bài** cho tầng Gold, là con số vô nguồn và **đã bị số đo thật bác bỏ**. Hai vệt audit cho ra **39.600** và **30.800–60.000** token mỗi bài, tức lệch **21 đến 90 lần**.
   - Nguyên nhân lệch không nằm ở nội dung mà ở **số bước**: mỗi bước gửi lại toàn bộ lịch sử, nên chi phí tăng theo bình phương số bước chứ không theo số bài.
   - Từ nay chi phí đọc từ bảng `token_ledger` trong `harness.db`:
     ```powershell
     & "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py report
     & "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py verify
     ```
   - **Tuyệt đối không ước lượng chi phí bằng cách nhân định mức với số bài.** Nếu sổ cái chưa có dòng nào thì câu trả lời đúng là "chưa đo", không phải một con số nhân ra.
2. **Ba Rổ Token Và Hai Thước Đo**:
   - Ba rổ rời rạc: đầu vào **trúng** bộ nhớ đệm, đầu vào **trượt** bộ nhớ đệm, và đầu ra. Đơn giá chênh nhau tới 200 lần nên cộng gộp là sai.
   - Hai thước: `quota_tokens` là tổng token tính vào hạn mức tài khoản, `billed_usd` là tiền. Chúng lệch nhau rất xa. **Mọi báo cáo phải nói rõ đang dùng thước nào.**
   - Giá nằm ở `project/config/token_pricing.yaml`, không hardcode ở đâu khác.
3. **Token là số ghi nhận, không phải cổng (ADR 0010, AGENTS.md §7.2)**:
   - Không có trần, ngưỡng cảnh báo hay hạn mức token theo bài, lô, đợt hay ngày. Không dừng đợt, không giảm số bài, không chia nhỏ lô vì token.
   - Packet mang trọn nội dung bài (trần chắt lọc đã tắt, `DEFAULT_MAX_TOKENS_PER_ARTICLE = 0`); chỉ bỏ link, ảnh, menu. Subscriber-gating, phễu L1/Gold bốn tầng và trần 2.200 ký tự thuộc lane đã ngừng.
   - Chia lô chỉ bằng `--batch` của `article_run.py`; lô trả thiếu bài thì `--repair` vá đúng phần thiếu.
4. **Đòn bẩy chi phí thật**:
   - Giữ tiền tố cache: persona trong preset phải khớp prefix từng byte (`build_article_prefix.py --check`); sổ cái báo **bộ nhớ đệm TRƯỢT** khi `hit` thấp hơn sàn `tiền tố × (số lượt − 1)`.
   - Xếp đợt lớn vào giờ thấp điểm (`.agents/dsh/DSH-VIEC-THU-CONG.md` mục 9).

---

## 2. Quy Trình Đo Lường (Auditing Workflow)

```
[Sau mỗi đợt hoặc cuối ngày]
       │
       ▼
[Bước 1: Đọc số thật] token_ledger.py report · pipeline_radar.py token --wave <đợt>
       │
       ▼
[Bước 2: Đối soát] token_ledger.py verify (sáu luật kế toán) · estimate_wave.py --wave <đợt> (sai số dự toán)
       │
       ▼
[Bước 3: Dấu hiệu kỹ thuật] turns_max > 1 · reasoning > 0 · cache TRƯỢT · output_tokens đứng ở một mức
```

Báo cáo chép nguyên con số của sổ cái, nói rõ đang dùng thước `quota_tokens` hay `billed_usd`, và không nhận xét con số là "cao" hay "vượt".

---

## 3. Bộ Công Cụ Cơ Học Thực Thi (Execution Tooling)

```powershell
# cwd = project/
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token                     # hôm nay
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token --date YYYY-MM-DD   # một ngày
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token --wave <đợt>        # một đợt
& "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py report --date today
& "C:\venvs\news-scape\Scripts\python.exe" scripts/estimate_wave.py --wave <đợt>
```
