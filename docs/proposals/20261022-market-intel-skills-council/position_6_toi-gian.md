# Vị trí 6 — Tối giản

## Kết luận chính

1. 12 skill chỉ gọi **7 lens thật** (`timeline`, `window`, `buzz`, `pulse`, `themes`, `cooccur`, `brief`). Có 4 skill dùng `timeline` và 2 skill dùng `cooccur`; các skill trong mỗi nhóm chỉ khác nhau ở `--target`, `--keywords` hoặc `--days`. Đây là cùng một lens, chỉ khác tham số, nên tách thành nhiều skill là thừa.
2. `news-ticker-screener` gọi lens cũ `ticker`, vốn chỉ là `timeline` không gộp story, không có mức nền và không có `periods`. Nên bỏ skill này.
3. Có 3 lens cũ mà không skill nào gọi (`urgent`, `sector`; `ticker` chỉ còn screener dùng), cùng 6 tham số CLI không skill nào dùng.
4. Đề xuất **6 skill**, gọi bằng câu tiếng Việt tự nhiên thay cho 12 tên `news-*` mà analyst khó nhớ.

## Bằng chứng

**Skill → lệnh `$LH` → tham số khác biệt**

| Skill | Lệnh | Khác biệt duy nhất |
|---|---|---|
| ticker-timeline | `timeline --target HPG --grain week` (`skills/news-ticker-timeline/SKILL.md:17-18`) | target = mã |
| catalyst-tracker | `timeline --target BSR --keywords "Dung Quất" --days 365 --grain month` (`skills/news-catalyst-tracker/SKILL.md:19-22`) | thêm `--keywords`, 365 ngày |
| macro-timeline | `timeline --target ty_gia --days 180 --grain week` (`skills/news-macro-timeline/SKILL.md:18-20`) | target = chủ đề |
| ticker-screener | `ticker --symbol X --limit 15` (`skills/news-ticker-screener/SKILL.md:23`) | ≈ `timeline --days 7` |
| sector-impact | `cooccur --target gia_thep --kinds TICKER,IND_GICS3` (`skills/news-sector-impact/SKILL.md:18-20`) | target = chủ đề ngành |
| geo-link | `cooccur --target MACRO_GEO:MY --kinds IND_GICS3,TICKER` (`skills/news-geo-link/SKILL.md:18-20`) | target = quốc gia |
| buzz-radar | `buzz --kind ...` (`skills/news-buzz-radar/SKILL.md:17-20`) | — |
| theme-trend | `themes --kind IND_GICS3` (`skills/news-theme-trend/SKILL.md:17-20`) | cùng hỏi "cái gì đang nóng" như buzz |
| sentiment-pulse | `pulse` (`skills/news-sentiment-pulse/SKILL.md:17-19`) | — |
| price-explainer | `window` (`skills/news-price-explainer/SKILL.md:17-18`) | — |
| daily-brief | `brief` (`skills/news-daily-brief/SKILL.md:17-19`) | đã gọi sẵn `buzz` bên trong (`tools/lakehouse_client.py:974`) |
| lakehouse-explorer | `status`, `query` | — |

Bản thân README cũng xác nhận các skill trùng lens: cột "Lens" ghi `timeline` ×3 và `cooccur` ×2 (`plugins/fpts-market-intel/README.md:20-29`). Mọi skill đều theo cùng một khuôn "Đối tượng + Thời gian + Câu hỏi" (`README.md:16`). Như vậy cách chia skill hiện nay theo **loại target**, trong khi lẽ ra phải chia theo **câu hỏi**.

**Mã thừa trong `tools/lakehouse_client.py` (1.179 dòng)**
- `query_ticker`, `query_urgent` và `query_sector_pulse` chiếm khoảng 75 dòng (`:372-446`). Phần CLI tương ứng (`:1026-1037`) và nhánh in bảng `--json`/`_format_table` (`:1117-1140`, `:996-1007`) cộng thêm khoảng 40 dòng. `urgent` chỉ là `brief`/`pulse.hot` rút gọn; `sector` (14 ngày, không phân vị) bị `pulse` bao trùm hoàn toàn. Không skill nào gọi `urgent` hay `sector`. `news-sentiment-pulse/SKILL.md:30` có nhắc tới `urgent`, nhưng lệnh này chỉ trả về tin mới nhất, không lọc theo kỳ, nên tham chiếu đó sai.
- Có hai chế độ xuất (bảng và JSON) chỉ áp dụng cho 4 lệnh cũ; 9 lens mới chỉ xuất JSON (`:1149-1171`). Chỉ cần giữ JSON.
- **Tham số không skill/README nào dùng**: `window --no-related` (`:1063`), `buzz --lookback` và `--z-min` (`:1067,1071`), `pulse --to` và `--history-days` (`:1074,1078`), `themes --as-of` (`:1083`), `cooccur --as-of` (`:1089`). Nên giữ ở dạng hằng số và bỏ khỏi CLI.
- `themes-list` (`:1047`) trùng với `lookup` về mặt chức năng tra mã; có thể gộp thành `lookup` có trả thêm danh sách theme.

**Quy tắc và văn bản**
- `rules/AGENTS.md` dài 42 dòng nhưng mục 2 (BOTH/LLM_ONLY/CODE_ONLY, `rules/AGENTS.md:10-14`) và định nghĩa sentiment (`:17-20`) là kiến thức pipeline, analyst không ra quyết định dựa trên chúng. Chỉ cần giữ mục 1, 5, 6, 7.
- Mỗi skill lặp lại dòng `$LH = ...` cùng phần mô tả JSON. Hai skill cũ còn dùng cú pháp `%USERPROFILE%` của cmd trong khối PowerShell (`skills/news-ticker-screener/SKILL.md:23`, `skills/news-lakehouse-explorer/SKILL.md:21,30`). Phong cách giữa các skill vì vậy không nhất quán.
- `plugin.json:6-11` chỉ có 6 suggestedPrompt. Con số này đã gợi ý rằng 6 câu hỏi là đủ để phủ các use case.

## Bộ skill đề xuất

| Skill mới | Gộp từ | Use case | Câu hỏi mẫu tiếng Việt |
|---|---|---|---|
| `tin-ma` (`timeline`) | ticker-timeline, catalyst-tracker, ticker-screener, macro-timeline | Dòng sự kiện của **bất kỳ** đối tượng (mã, chủ đề, quốc gia, từ khoá) trong một khoảng thời gian; `--keywords` dùng để theo dõi catalyst; mặc định 7 ngày cho câu hỏi "tin mới" | "HPG 3 tháng qua có gì?", "Dự án Dung Quất của BSR tiến độ sao?", "Tỷ giá 6 tháng qua diễn biến thế nào?" |
| `vi-sao-bien-dong` (`window`) | price-explainer | Giải thích một phiên tăng trần, giảm sàn hoặc khối lượng đột biến | "Vì sao VHM giảm sàn ngày 15/05?" |
| `cai-gi-dang-nong` (`buzz` + `themes`) | buzz-radar, theme-trend | Mã, ngành hoặc chủ đề nóng bất thường (theo ngày) và nóng lên hay nguội đi (7/30/90 ngày) | "Hôm nay mã nào nóng tin?", "Câu chuyện nào đang nóng lên tuần này?" |
| `tam-ly-tin` (`pulse`) | sentiment-pulse | Mức độ lạc quan hay bi quan so với phân vị 1 năm | "Tin tức tuần này bi quan hơn mọi khi không?" |
| `ai-bi-anh-huong` (`cooccur`) | sector-impact, geo-link | Một sự kiện, đầu vào hoặc quốc gia liên quan đến những ngành và mã nào | "Mỹ áp thuế thì ngành nào bị ảnh hưởng?", "Giá thép tăng tác động mã nào?" |
| `ban-tin-sang` (`brief`) | daily-brief | Bản tin sáng theo watchlist | "Lập morning brief cho HPG, VCB, FPT" |

`lakehouse-explorer` (`status`, `query`) không nên là skill dành cho analyst. Nên chuyển nó vào README/quy tắc làm công cụ cho Quant, và mọi skill tự gọi `status` khi cần. Sau khi gộp, CLI còn 9 lệnh: `status`, `lookup`, `query` cùng 6 lens.

Analyst không cần nhớ tên skill. Câu tự nhiên ("tin…", "vì sao…", "cái gì nóng…", "tâm lý…", "ai bị ảnh hưởng…", "bản tin sáng") đã tự khớp với 6 phần mô tả.

## Không nên làm

- Không thêm skill mới cho từng team hay từng loại target (ví dụ "tin ngân hàng", "tin BĐS"). Đó vẫn chỉ là `timeline` với target khác.
- Không thêm lens mới trước khi có log sử dụng thật cho thấy 6 câu hỏi trên không đủ.
- Không mở rộng `config/themes.json` (hiện 125 dòng) thành taxonomy lớn. Từ khoá tự do trong `--target` đã đủ dùng.
- Không thêm chế độ xuất bảng, tham số tinh chỉnh thống kê (z, lookback, history) hay dữ liệu giá vào plugin.
- Không viết lại phần định nghĩa pipeline (BOTH/LLM_ONLY) trong mỗi skill.
- Không giữ lại lens cũ chỉ để "tương thích ngược": plugin chưa có người dùng phụ thuộc vào `ticker`, `urgent` hay `sector`.
