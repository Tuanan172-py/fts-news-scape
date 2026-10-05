---
name: watchlist-curator
description: Chuyên viên quản trị danh mục theo dõi người dùng (Watchlists), đồng bộ manifest.yaml, phân tầng Ticker 3 Tiers và phát hiện thực thể mới (Human-in-the-loop).
---

# Watchlist & Entity Curator Agent Skill

> **Mục tiêu cốt lõi:** Đảm bảo hệ thống luôn hiểu đúng và đủ danh mục người dùng mong muốn; bảo vệ kho từ điển thực thể (Ontology) khỏi ô nhiễm rác và triệt tiêu 100% false positive với từ tiếng Việt thông dụng.

---

## 1. Định Hướng & Bất Biến Nghiệp Vụ (Context & Domain Invariants)

1. **Ranh Giới Người Dùng (Zero Hallucination User Manifest)**:
   - Hệ thống CHỈ công nhận và xử lý cho các người dùng được định nghĩa chính thức trong:
     - `project/config/entities/users/<username>.yaml`
     - `project/config/entities/manifest.yaml`
   - Tuyệt đối không sinh thêm người dùng ảo.
2. **Kiến Trúc Phân Tầng Cổ Phiếu Ticker 3 Tiers (US-014)**:
   - **Tier 1 (Core Universe — 742 mã)**: 100% mã trong Watchlist của người dùng đang active + doanh nghiệp lớn vốn hóa $\ge 300$ tỷ VND. Được nhận diện bình thường qua mã 3 ký tự in hoa và alias thương hiệu.
   - **Tier 2 (Extended Universe — 351 mã)**: Doanh nghiệp vốn hóa 100 – 300 tỷ VND. Chỉ nhận diện qua mã khi là công bố thông tin đầu dòng (`MÃ: ...`), trong văn bản thông thường bắt buộc nhận diện qua alias thương hiệu để chống nhầm lẫn từ tiếng Việt.
   - **Tier 3 (Archived / Dormant — 891 mã)**: Đã cô lập độc lập tại `data/entities/entities_archive.json`. Loại bỏ 100% khỏi runtime `entities.json`.
3. **Quy Tắc Chặn Từ (Stoplist & Guards)**:
   - Áp dụng nghiêm ngặt `GENERIC_ALIAS_STOPLIST` (loại bỏ alias địa danh như "Việt Nam", "Hà Nội", "Xây dựng" gán nhầm cho cổ phiếu).
   - Áp dụng `Capitalized Suffix Guard` (chặn các địa danh như "Mỹ Tho", "Mỹ Thuận" bị bắt nhầm thành mã MYG).

---

## 2. Quy Trình Vận Hành & Mô Hình Giám Sát (Curator Workflow)

```
[Quét Định Kỳ Thư Mục Subscriptions] (users/subscriptions/*.xlsx)
       │
       ▼
[Bước 1: Phát hiện Tệp Đăng Ký Mới (Subscription Discovery)]
  ├── Tìm thấy file <user>_news.xlsx mới xuất hiện
  └── Đối chiếu với config/entities/manifest.yaml
       │
       ├─► Nếu CHƯA CÓ trong manifest:
       │     👉 Báo cáo Dev: "Phát hiện file đăng ký mới của <user>. Cần thêm vào manifest.yaml để kích hoạt."
       │
       └─► Nếu ĐÃ CÓ: Tiến hành kiểm tra danh mục theo dõi
       │
       ▼
[Bước 2: Giám Sát Thực Thể Mới Từ Subagents L1 (Unlisted Entity Scouting)]
  ├── Trích xuất mảng unlisted_candidates từ các l1_outputs gần nhất
  ├── Lọc các thực thể xuất hiện với tần suất cao (>= 3 lần/tuần)
  └── Đề xuất Dev: Bổ sung thực thể mới vào config/entities/aliases/ hoặc catalog chính thức.
```

---

## 3. Bộ Công Cụ Cơ Học Thực Thi (Execution Tooling)

```powershell
# 1. Kiểm tra trạng thái đồng bộ người dùng và phát hiện file đăng ký mới:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py users

# 2. Biên dịch lại từ điển thực thể khi có cập nhật Watchlist hoặc vốn hóa:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/build_entities.py

# 3. Biên dịch cấu hình đăng ký người dùng:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/compile_users.py
```

---

## 4. Cơ Chế Nhắc Nhở Cho Developer (HITL Prompts)

Khi phát hiện người dùng mới hoặc cần bổ sung mã cổ phiếu, Curator Agent đưa ra hướng dẫn chuẩn:
```text
⚠️ PHÁT HIỆN NGƯỜI DÙNG MỚI:
Phát hiện tệp 'users/subscriptions/GiangNT_news.xlsx' đã được tạo nhưng chưa khai báo.
👉 Hành động đề xuất:
1. Mở 'project/config/entities/manifest.yaml' và thêm:
   users:
     GiangNT: true
2. Chạy: & "C:\venvs\news-scape\Scripts\python.exe" scripts/compile_users.py
```
