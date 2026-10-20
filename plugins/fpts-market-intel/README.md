# FPTS Market Intel — Unified Lakehouse Plugin

Plugin khai phá dữ liệu tin tức tài chính đã qua xử lý LLM, dành cho chuyên viên phân tích FPTS trên nền tảng **Antigravity (AGY)** và **Gemini IDE**.

---

## 1. Tính Năng Nổi Bật

- **Zero-Token Local Execution**: DuckDB nhúng quét trực tiếp Parquet (OBT) trên máy trạm; tầng lọc, đếm, so mức nền không tốn token LLM. LLM chỉ đọc gói bằng chứng đã cô đọng.
- **Zero-Config Auto-Discovery**: Tự nhận diện shortcut SharePoint OneDrive (`FRA_DataIngestion - news-data`).
- **Truy hồi theo thực thể**: View `article_entities` hợp nhất `entities` và `symbols`, nên lọc theo mã/ngành/chủ đề vĩ mô bắt được cả bài chỉ nhắc đối tượng trong nội dung.
- **Đếm theo story**: Bài cùng tiêu đề chuẩn hoá giữa các báo gộp thành một story; số nguồn đăng là thước đo lan toả.

## 2. Bản Đồ Kỹ Năng Theo Team

Mọi kỹ năng dùng chung một khuôn: **Đối tượng** (mã / ngành / chủ đề) + **Khoảng thời gian** + **Câu hỏi**.

| Team | Kỹ năng | Tình huống | Lens |
|---|---|---|---|
| Cơ bản | `news-ticker-timeline` | Dòng sự kiện của một mã trong [từ–đến] cho báo cáo Update | `timeline` |
| Cơ bản | `news-catalyst-tracker` | Tiến độ dự án/luận điểm 6–12 tháng, phát ngôn so với thực tế | `timeline --keywords` |
| Cơ bản | `news-sector-impact` | Tin ngành/đầu vào ảnh hưởng mã nào | `cooccur` |
| Cơ bản / Tư vấn | `news-ticker-screener` | Tin mới nhất của một mã | `ticker` |
| Thị trường / Kỹ thuật | `news-buzz-radar` | Mã có lượng tin đột biến so với 20 phiên | `buzz` |
| Thị trường / Kỹ thuật | `news-sentiment-pulse` | Tâm lý tin tức và phân vị 1 năm, tin cấp thiết | `pulse` |
| Thị trường / Kỹ thuật | `news-price-explainer` | Giải thích một phiên biến động giá (T-3…T+2) | `window` |
| Vĩ mô | `news-macro-timeline` | Biên niên chủ đề vĩ mô / địa chính trị 3–6 tháng | `timeline` |
| Vĩ mô | `news-theme-trend` | Câu chuyện đầu tư nóng lên hay nguội đi (7/30/90 ngày) | `themes` |
| Vĩ mô | `news-geo-link` | Sự kiện địa chính trị liên quan ngành/mã Việt Nam | `cooccur` |
| Morning | `news-daily-brief` | Bản tin sáng ba tầng | `brief` |
| Quant | `news-lakehouse-explorer` | Kiểm tra độ tươi, SQL tùy biến | `status`, `query` |

## 3. Lệnh Lens (`tools/lakehouse_client.py`)

```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH status
python $LH lookup --text "lai suat"
python $LH timeline --target HPG --days 90 --grain week
python $LH window   --target VHM --date 2026-05-15
python $LH buzz     --top 10
python $LH pulse    --days 30
python $LH themes
python $LH cooccur  --target MACRO_GEO:MY --kinds IND_GICS3,TICKER
python $LH brief    --watchlist HPG,VCB,FPT
```

`--target` nhận mã cổ phiếu (`HPG`), mã thực thể (`MACRO_GEO:MY`, `IND_GICS3:NGAN_HANG`), tên chủ đề trong `config/themes.json` (`dau_tu_cong`) hoặc từ khoá tự do (`"Dung Quất"`).

## 4. Cấu Hình Chủ Đề

`config/themes.json` định nghĩa các câu chuyện đầu tư và chủ đề vĩ mô bằng tập thực thể và từ khoá. Analyst có thể thêm chủ đề mới mà không cần sửa mã.

## 5. Kiểm Tra Đường Dẫn Dữ Liệu

- **SharePoint Site**: `https://fptscomvn.sharepoint.com/sites/FRA_DataIngestion`
- **Thư mục cục bộ chuẩn**: `%USERPROFILE%\OneDrive - fpts.com.vn\Shortcuts\FRA_DataIngestion - news-data`
- Có thể đặt biến môi trường `NEWS_DATA_ROOT` trỏ tới thư mục trên.

## 6. Cấu Trúc Thư Mục

```text
fpts-market-intel/
├── plugin.json            # Manifest & suggestedPrompts
├── README.md
├── config/themes.json     # Từ điển chủ đề do analyst cấu hình
├── rules/AGENTS.md        # Guardrails: căn cứ dữ liệu, đo lường vs diễn giải, mức nền
├── skills/                # 12 kỹ năng theo team
└── tools/lakehouse_client.py   # DuckDB nhúng, view phân tích và các lens
```
