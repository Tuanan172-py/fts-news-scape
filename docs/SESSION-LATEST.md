# Bàn giao Phiên Vận Hành (Session Handoff)

**Thời điểm:** 2026-11-27 15:02 +07:00
**Nhiệm vụ hoàn tất:** Hoàn thành và bàn giao toàn bộ mốc **M1** (trước hạn `27/11/2026 17:00`) cho lượt đồng bộ `article-compact-v3` trên `Research-FPA/news-scraper`.

---

## 1. Trạng thái Mốc M1 & Giao tiếp GitHub (Đã hoàn tất)

- **Gói M1 cố định trên `fpa`:** nhánh **`import/clean-20261126`**, đầu nhánh **`e925b6b`** (`e925b6bdaf1d199043ea8afe902494a6a7315e12`); nhánh cũ `import/clean-20261123` (`c99f755`) giữ nguyên không force-push.
- **Đã đăng phản hồi hoàn thành M1 (sau duyệt Operator, 0 PII):**
  - Issue `#10`: `https://github.com/Research-FPA/news-scraper/issues/10#issuecomment-7213026174`
  - Issue `#8`: `https://github.com/Research-FPA/news-scraper/issues/8#issuecomment-7213025511`
- **Kiểm định trên `e925b6b`:** `pytest project/tests/` (`NEWS_SCAPE_PRODUCTION_HOST=""`) `1.255 passed, 21 skipped, 0 failed`; `--check-prefix` đạt (`80c6edfe7891330b`); quét AST cô lập `382` tệp `.py` / `0` vi phạm; `doc lint` `0` lỗi; `overlap.py` theo tổ tiên chung Git `3931ac9` so với `fpa-toolkit/main` `7e62c439`: `73 | 129 | 44 | 38 | 6` (`article_expand.py` giữ cả hai).
- **Trạng thái `dev/us038`:** đã gộp nhánh tài liệu `m1/docs-20261126` (`US-057`, `US-059`, `plan.md` P5/P7/P8 + dữ liệu đo `p7_{results,summary}.json`, `TEST_MATRIX.md`) cùng `US-060` (tắt đồng bộ `monocle_review_*.db` lên SharePoint, giảm tần suất `.probe` còn 4 lần/ngày). **Cờ `article.contract` vẫn mặc định `v2`**; `m1/us058-v3` (`d4ec23e`) và `US-058` giữ riêng tới M3.

---

## 2. Trạng thái Production Live (`27/11 13:29`)

- **`ops_daemon`:** Sống, mandate `L1` (hạn `18/12/2026`), breaker `CLOSED`; sau bản vá `US-059` (`a78ed30`) hoàn tất `78/78` đợt mới (`DONE`), sáng `27/11` (`09:10–09:44`) tự phục hồi bình thường sau 3 lỗi `429` của `agy` (không kẹt vòng lặp).
- **`FRA - Data/news` (`27/11 12:51`):** `obt/2`, `64.393` bài viết trên `926` phân vùng (`2017-05-04..2026-11-27`), **`47` lần `research.published`** (`+2` `research.unchanged`), **`0` lỗi phân vùng**, `12/12` ngày (`16–27/11`) sạch `CODE_ONLY`, SHA-256 `_catalog/entities.json` (`485b4650...`) khớp 3 chiều.

---

## 3. Việc Kế Tiếp (Chờ M2 & Chuẩn Bị M3)

1. **Chờ M2 từ phía `fpa-toolkit`:** anh Đức chạy `satellite_sync pull` từ `import/clean-20261126` (`e925b6b`), gỡ `xfail` HSG, kiểm `--check-prefix`, merge vào `fpa-toolkit/main`, đóng PR `#7` và Issue `#5`.
2. **Sau khi M2 merge xong:** mở PR `import/clean-20261126 -> news-scraper/main` (`0b67733`).
3. **Bốn điều kiện bắt buộc trước khi bật `article.contract: v3` (M3):**
   - Khắc phục lỗi bỏ sót trường `x` (`missing:x`) theo lô;
   - Thử nghiệm cỡ lô `25` so với `50` để giảm cắt cụt và chi phí chạy sửa lỗi (`+57,5%` ở đỉnh `v2`, ước tính `v3 ~15,5–17,5M` token/ngày);
   - Đo lại mẫu phân tầng có tính đủ chi phí sửa lỗi và xác nhận biên chịu tải hạn mức `agy` / runner dự phòng;
   - Hoàn thiện quy tắc gắn nhãn `low-confidence` cho `direction` ngoài ticker (ADR-0028).
4. **Hạng mục tách riêng sau M1/M3:** sửa `build_entities.py` (`DataFrame` không có `ticker`), tổng hợp lại (`re-consolidate`) `665/926` phân vùng cũ (đến `15/11/2026`), và các thao tác thủ công tùy chọn trên OneDrive/SharePoint của `US-060` (bỏ chọn `Desktop > backup` trên OneDrive UI, dọn Recycle Bin `FRA_DataIngestion`, xóa `C:\data\news-scape\archive\onedrive-stuck-reviews-20261126\` khi không cần đối chiếu).
