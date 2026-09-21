# RUNBOOK — Article Lane trên DSH

|  |  |
| --- | --- |
| Áp dụng từ | 2026-09-18 |
| Thay thế | Quy trình L1 → Gold hai tầng trong `RUNBOOK.md`. Quy trình cũ giữ lại để quay lui |
| Thiết kế | `plans/20260918-1651-article-lane-unified/plan.md` |
| Lưu đồ vận hành | [`WORKFLOW-article-lane.md`](WORKFLOW-article-lane.md) — sáu lưu đồ: toàn cảnh đợt, trình tự gọi, bên trong chương trình điều phối, vòng đời token, cây quyết định sự cố, ranh giới máy/LLM/người |
| Bề mặt DSH | `docs/proposals/dsh-surface-verified-2026-09-18.md` |

> **Một đợt = một mục tiêu = một phiên.** Xong đợt thì đọc bàn giao và đóng phiên. Mở phiên mới rẻ hơn mang theo ngữ cảnh đã phình, vì bộ nhớ đệm nằm ở phía nhà cung cấp chứ không gắn với phiên.

---

## 0. Chuẩn bị một lần

**Bước 1 — nối preset vào DSH** (nếu chưa làm):

```powershell
cmd /c mklink /J "$env:USERPROFILE\.dsh\.agent-presets\news-scape-conductor" ^
  "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape\.agents\dsh\presets\news-scape-conductor"
```

**Bước 2 — sinh prefix và dán vào preset:**

```powershell
cd project
& "C:\venvs\news-scape\Scripts\python.exe" scripts/build_article_prefix.py
```

Mở tệp vừa sinh tại `project/data/prefix/ARTICLE_SYSTEM_CORE.md`, chép **trọn nội dung** vào trường `persona` của row `tool-subagent-article` trong `agent.cordis.yml`.

Dán xong thì xác nhận ngay, đừng tin mắt:

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/build_article_prefix.py --check-preset
```

Đây là việc thủ công duy nhất của cả quy trình, và nó chỉ phải làm lại khi danh mục thực thể đổi. Từ 21/09, `build_article_prefix.py --check` kiểm **hai** vế: tệp còn khớp danh mục, **và** persona trong preset còn khớp tệp từng byte. Vế thứ hai mới là vế giữ bộ nhớ đệm — persona dán thiếu một dòng thì kết quả vẫn đúng, chỉ có hoá đơn đắt lên gấp năm mươi lần ở phần lẽ ra rẻ nhất, và không có triệu chứng nào khác. Trước đây vế ấy không ai kiểm.

Danh sách đầy đủ những việc chỉ làm được bằng tay trong DSH: [`DSH-VIEC-THU-CONG.md`](DSH-VIEC-THU-CONG.md).

**Bước 3 — mở phiên đúng preset.** Settings → General → Agent preset → **News-Scape Conductor**, rồi tạo phiên mới với quyền `workspace-write`.

Sai preset là mất toàn bộ ranh giới công cụ của agent con. Đây đúng là nguyên nhân gốc của vệt 845 nghìn token ngày 17/09, không phải một rủi ro lý thuyết.

---

## 1. Chạy một đợt

### 1.1 Chuẩn bị — chạy ở terminal, 0 token

```powershell
cd project
& "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave W01 --today --limit 100 --batch 100
```

Lệnh này kiểm prefix, đóng gói packet, in dự toán và sinh sẵn chương trình điều phối. Nó **không gọi mô hình**.

**`--batch` là cổng chia lô duy nhất.** Không trần token nào can thiệp. Đặt `--limit 100 --batch 100` thì được đúng một lượt gọi cho trọn trăm bài.

Ba cổng từng chia lô hộ bạn đã gỡ hết ngày 21/09: `maxTokens` trong preset, bộ chia theo ngân sách đầu ra, và trần ngữ cảnh 25%. Lý do gỡ nằm ở §16 của plan. Tóm tắt: ngữ cảnh chưa bao giờ là ràng buộc — trăm bài chiếm 25% cửa sổ kể cả khi đọc trọn nội dung. Còn trần đầu ra thật của DSH là **256.000 token mỗi request** (`DEFAULT_MAX_TOKENS = 256e3`, con kế thừa của cha khi row không đặt gì), trong khi trăm bài chỉ cần khoảng 90.000. Con số 40.000 cũ là do **dự án tự đặt**, không phải của nhà cung cấp.

**Cơ chế thay thế là vá sau, không phòng trước.** Gửi trọn lô. Nếu lượt nào trả về thiếu bài thì `article_run.py --wave <mã> --repair` đối chiếu số bản ghi nhận được với số bài đã gửi, đóng gói lại **đúng phần thiếu**, và sinh chương trình chạy bù. Chi phí tỉ lệ với thứ thật sự mất chứ không tỉ lệ với nỗi lo.

Sổ cái vẫn theo dõi `output_tokens` mỗi lượt. Nếu con số ấy đụng một mức rồi đứng yên qua nhiều đợt thì đó là trần thật đang lộ ra, và khi ấy mới có số liệu để bàn tới chia lô.

### 1.2 Chạy mô hình — trong phiên DSH

Mở tệp `project/data/agent_tasks/article/wave_W01.conductor.ts` và dán **trọn nội dung** vào **một** lệnh `run_code`.

Đừng tách thành nhiều bước. Toàn bộ chi phí của phiên điều phối tỉ lệ với số bước chứ không tỉ lệ với số bài; tách một chương trình thành năm bước là nhân chi phí lên nhiều lần mà không được gì.

Chương trình tự làm: gọi một lượt **hâm bộ nhớ đệm** tí hon, rồi đọc packet theo cửa sổ dòng, chạy **mọi** lô song song, và ghi kết quả thẳng ra đĩa. Nó chỉ trả về vài con số, nên nội dung của lô không lọt vào ngữ cảnh phiên.

Lượt hâm cache thay cho cách cũ là bắt lô đầu chạy một mình. Bộ nhớ đệm chỉ được ghi khi có một request thật đi qua, nhưng request ấy không cần mang trăm bài: một packet một bài rác ghi đúng phần tiền tố tĩnh trong vài giây, thay vì bắt cả đợt chờ trọn một lô. Tiền không đổi, thời gian chạy đợt ngắn lại đúng bằng thời gian của một lô.

Đợt **một lô** thì chương trình không hâm, và đó là chủ ý: không có lô thứ hai để dùng lại tiền tố, nên lượt hâm chỉ dời đúng khoản token ấy sang một request khác rồi tính thêm một bản ghi đầu ra. Cấu hình mặc định `--limit 100 --batch 100` rơi vào đúng trường hợp này.

### 1.3 Vá phần thiếu, nếu có — 0 token

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave W01 --repair
```

Ba trạng thái, mỗi trạng thái một câu trả lời riêng: **chưa lô nào có đầu ra** thì lệnh nói thẳng là chưa có gì để đối chiếu và thoát mã 2 (chạy chương trình điều phối trước đã); **đủ bài** thì báo không cần vá; **thiếu bài** thì ghi packet bù và một tệp `wave_W01.repair.ts` — chạy trọn tệp ấy trong một lệnh `run_code` rồi mới sang bước hoàn tất.

### 1.4 Hoàn tất — quay lại terminal, 0 token

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave W01 --finish
```

Lệnh này bung bản ghi, nạp cơ sở dữ liệu, ghi sổ cái token, sinh tệp bàn giao và đo áp suất ngữ cảnh.

### 1.5 Giao hàng

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --date today
```

Lệnh này in luôn thư mục đã ghi. Cần biết đường dẫn mà chưa muốn chạy thì hỏi thẳng hợp đồng, 0 token:

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --where
```

Thư mục giao hàng nằm ở **gốc kho**, không nằm trong `project/`. Đừng đi dò bằng cách đọc mã nguồn hay liệt kê thư mục: vệt ngày 21/09 tốn sáu bước mô hình chỉ để tìm lại đúng một đường dẫn mà lệnh trên in ra tức thì.

---

## 2. Đọc số sau mỗi đợt

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token --wave W01  # phân rã hoá đơn + kiểm cache
& "C:\venvs\news-scape\Scripts\python.exe" scripts/estimate_wave.py --wave W01   # dự toán đối chiếu số thật
& "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py report        # sổ cái
& "C:\venvs\news-scape\Scripts\python.exe" scripts/ctx_probe.py                  # áp suất ngữ cảnh
```

`radar token` nay đọc thẳng sổ cái và checkpoint phiên DSH. Trước 21/09 nó nhân số bài với hai định mức chết 450 và 1.470 token mỗi bài rồi nhân tiếp với một đơn giá gõ trong mã, không biết bộ nhớ đệm tồn tại — nên nó và sổ cái đưa ra hai con số khác nhau cho cùng một đợt. Con số của nó khi ấy phải bỏ hết, đừng đem so với bất cứ báo cáo cũ nào.

Bảy dấu hiệu cần xử lý ngay:

| Dấu hiệu | Nghĩa là gì | Làm gì |
|---|---|---|
| `turns_max > 1` | Worker không xong trong một bước, nó đã sa vào viết chương trình | Soi lại phần đầu persona: đoạn tuyên bố không có tool phải đứng trước và phải rõ |
| `reasoning > 0` | Chế độ suy luận chưa tắt, đang tính tiền theo giá đầu ra | Đặt `reasoningEffort: "off"` cho row worker — **phải có dấu nháy**, vì YAML đọc `off` trần thành boolean `false` chứ không thành chuỗi |
| `token/bài` vượt 2.500 | Hoặc mốc quy kết quá rộng nên gộp nhầm phiên khác, hoặc packet quá dày | Kiểm số phiên được gộp trong dòng sổ cái trước, rồi mới soi histogram của `article_pack`. Mức bình thường đo được khoảng 1.980 |
| Lô trả về thiếu bài | Lượt đó bị cắt cụt | `--repair` đóng gói lại đúng phần thiếu. Đừng chia nhỏ mọi lô để phòng xa |
| `output_tokens` nhiều lượt bằng nhau y hệt | Đã chạm một trần nào đó | Ghi lại con số. Nếu là 256.000 thì đó là mặc định DSH; nếu khác thì có cấu hình nào khác đang đè |
| Áp suất vàng hoặc đỏ | Ngữ cảnh phiên đã phình | Đọc bàn giao, **đóng phiên**, mở phiên mới |
| Sổ cái báo **bộ nhớ đệm TRƯỢT** | `hit` thấp hơn sàn `tiền tố × (số lượt − 1)` | Kiểm theo thứ tự: `build_article_prefix.py --check` (persona lệch prefix là nguyên nhân số một) → có đổi tool set/model/effort giữa đợt không → phiên nào chạm ngưỡng nén 80% |

---

## 3. Bàn giao và đóng phiên

Tệp bàn giao mới nhất luôn ở `project/data/state/HANDOFF-latest.md`. Nó được sinh từ cơ sở dữ liệu với chi phí bằng không, nên không cần nhờ mô hình tóm tắt gì.

Phiên mới chỉ cần đọc tệp đó rồi chạy tiếp. Mất phiên giữa chừng chỉ mất đúng lô đang chạy, và packet của lô đó vẫn còn trên đĩa.

---

## 4. Khi có sự cố

| Triệu chứng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| `SubagentDepthError` ngay lần gọi đầu | `maxDepth: 0` cấm delegation hoàn toàn, không phải chặn đệ quy | Đặt `maxDepth: 1` |
| Con gọi được các tool khác | Phiên đang chạy sai preset | Đóng phiên, mở lại đúng preset. Không sửa prompt để chữa |
| Đầu ra của lô hỏng nhiều | Persona trôi hoặc trần token đầu ra quá thấp | `article_expand` đã cứu từng bản ghi; chạy lại đúng lô hỏng. Vượt 10% thì lệnh tự dừng đợt |
| `article_pack` báo dòng quá dài | Có đoạn văn vượt trần cắt dòng của công cụ đọc | Hạ `MAX_PARAGRAPH_CHARS` trong `src/agent/distill.py` rồi đóng gói lại |
| Prefix báo lệch danh mục | Danh mục thực thể đã đổi | Sinh lại prefix và dán lại vào persona. Bỏ qua là vỡ bộ nhớ đệm |
| Persona báo lệch prefix | Dán thiếu, dán thừa, hoặc trình soạn thảo tự thụt lề lại khối YAML | Dán lại trọn nội dung tệp prefix, rồi `--check-preset` để xác nhận. Đây là lỗi duy nhất không có triệu chứng nào ngoài hoá đơn |
| Sổ cái báo con số vô lý | Mốc quy kết gộp nhầm phiên DSH khác đang mở | Đóng các phiên không liên quan trước khi chạy đợt |

---

## 5. Quay lui về đường cũ

Đường L1 → Gold cũ vẫn gọi được: `agent_l1` và `agent_gold` còn trong preset, packet cũ chưa bị xoá, và các stage cũ chỉ bị đánh dấu ngừng dùng chứ không gỡ.

Điều kiện quay lui định lượng: tỷ lệ đạt cổng nghiệm thu dưới 95% **hoặc** tỷ lệ hỏng trên 10%, kéo dài **hai đợt liên tiếp**.

Chỉ dọn đường cũ sau khi đường mới chạy sạch trọn một chu kỳ vận hành đầy đủ.
