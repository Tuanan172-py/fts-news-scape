# RUNBOOK — Article Lane trên DSH

|  |  |
| --- | --- |
| Áp dụng từ | 2026-09-18 |
| Thay thế | Quy trình L1 → Gold hai tầng. Lane cũ ngừng hẳn từ 2026-09-23, xem §5 |
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

**`--batch` là cách chia lô duy nhất, và mặc định là tự chọn.** Bỏ hẳn cờ này thì đợt tự tính cỡ lô theo số bài thật: `batch = clamp(ceil(số_bài / 10), 100, 500)`.

Công thức giữ số lô bằng đúng `maxParallelSubCalls` mặc định của DSH là 10, nên mọi đợt tới 5.000 bài chạy trọn trong **một sóng song song**. Ít lô hơn thì bỏ phí năng lực song song; nhiều hơn thì các lô dôi ra phải chờ hết một sóng, mà thời gian đợt do lượt dài nhất quyết định.

| Số bài | Cỡ lô tự chọn | Số lô | Sóng |
| --: | --: | --: | --: |
| 415 · 455 | 100 | 5 | 1 |
| 1.000 | 100 | 10 | 1 |
| 2.000 | 200 | 10 | 1 |
| 5.000 | 500 | 10 | 1 |
| 10.000 | 500 | 20 | 2 |

Cận dưới 100 chặn chia vụn: lô vài bài vẫn tốn trọn một lượt gọi và một lần trả giá tiền tố. Cận trên 500 chặn lô quá dài: bản ghi cuối lô được sinh trong ngữ cảnh đã chứa toàn bộ bản ghi trước đó nên phần đuôi dễ trôi. Đặt `--batch <n>` cứng khi muốn ép một cách chia cụ thể.

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

Lệnh này bung bản ghi, nạp cơ sở dữ liệu, hậu kiểm, ghi sổ cái token, sinh tệp bàn giao và đo áp suất ngữ cảnh.

**Chỉ tin dòng kết và mã thoát.** Đợt xong khi lệnh thoát 0 và in `✅ ĐỢT <mã> HOÀN TẤT`. Có ba trường hợp in `❌ ĐỢT <mã> CHƯA HOÀN TẤT` và thoát 1:

- DB không ghi được, phát hiện **trước** khi nạp.
- Một lệnh nạp trả mã khác 0.
- Hậu kiểm thấy độ phủ của đợt dưới 90% ở một trong hai lớp.

Khung ❌ in sẵn đúng lệnh chạy lại. Ví dụ `--finish --only ingest,verify,ledger,handoff` chỉ chạy lại các bước từ nạp trở đi, không bung lại bản ghi và không ghi thừa dòng sổ cái. Tên bước hợp lệ: `expand`, `ingest`, `verify`, `ledger`, `handoff`.

Trước 23/09, hai lệnh nạp chạy với `check=False`. Đợt W365 vì thế in "HOÀN TẤT" và thoát 0 trong khi DB chưa nhận dòng nào. Lần nạp tay sau đó còn bỏ sót 31 bài.

Độ phủ phải đọc ở **bảng hậu kiểm**, vì bảng ấy đếm theo đúng tập bài trong bảng ánh xạ của đợt. Dòng `ingested: done=… failed=…` của hai lệnh nạp là số cộng dồn trên cả thư mục, gồm cả tệp tồn của lane cũ.

### 1.5 Giao hàng

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --date today
```

Lệnh này in luôn thư mục đã ghi. Cần biết đường dẫn mà chưa muốn chạy thì hỏi thẳng hợp đồng, 0 token:

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --where
```

Script nằm trong `project/scripts/` như mọi script khác, chạy với cwd = `project/`. Chỉ **thư mục đầu ra** `users/output/` là nằm ở gốc kho. Đừng đi dò bằng cách đọc mã nguồn hay liệt kê thư mục.

### 1.6 Hợp đồng đường dẫn và quyền ghi — một lệnh, 0 token

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --where
```

In python, cwd chuẩn, đường dẫn DB kèm kết quả **ghi thử thật** (ghi một bảng trong giao dịch rồi rollback), thư mục packet, thư mục đầu ra, tệp bàn giao, thư mục giao hàng và preset. DB không ghi được thì lệnh thoát 1 và nói thẳng nguyên nhân.

**Quyền ghi DB.** DB vận hành nằm ở `C:\data\news-scape\monocle.db`, **ngoài** kho mã. Sandbox `workspace-write` của DSH chặn ghi ra ngoài kho, và không có cấu hình nào mở rộng được: `writableRoots()` của `dsh-sandbox` chỉ gồm workspace root và thư mục tạm. SQLite khi ấy chỉ báo `attempt to write a readonly database`, nghe như lỗi thuộc tính tệp.

Phân quyền theo bước:

| Bước | Quyền |
|---|---|
| Radar, chuẩn bị đợt, chạy mô hình, `--repair` | `workspace-write` là đủ: chỉ đọc DB và ghi tệp trong kho |
| `--finish`, `write_user_output.py` | `danger-full-access` |

Thiếu quyền ở bước chuẩn bị thì lệnh chỉ in dòng ⓘ nhắc trước, không chặn. Thiếu quyền ở `--finish` thì lệnh dừng trước khi nạp, in ❌ và thoát 1. Không token nào bị mất, vì đầu ra của mô hình đã nằm trên đĩa: chạy lại `--finish` với đúng quyền là xong.

---

## 2. Đọc số sau mỗi đợt

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token --wave W01  # phân rã hoá đơn + kiểm cache
& "C:\venvs\news-scape\Scripts\python.exe" scripts/estimate_wave.py --wave W01   # dự toán đối chiếu số thật
& "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py report        # sổ cái
& "C:\venvs\news-scape\Scripts\python.exe" scripts/ctx_probe.py                  # áp suất ngữ cảnh
```

`radar token` nay đọc thẳng sổ cái và checkpoint phiên DSH. Trước 21/09 nó nhân số bài với hai định mức chết 450 và 1.470 token mỗi bài rồi nhân tiếp với một đơn giá gõ trong mã, không biết bộ nhớ đệm tồn tại — nên nó và sổ cái đưa ra hai con số khác nhau cho cùng một đợt. Con số của nó khi ấy phải bỏ hết, đừng đem so với bất cứ báo cáo cũ nào.

**Token là số ghi nhận, không phải cổng.** Không có giới hạn hay mức cảnh báo token nào, theo bài, theo lô hay theo đợt. Sổ cái và `radar token` ghi token và USD để người dùng tự đánh giá, tự ước lượng. Không dừng đợt, không giảm số bài, không chia nhỏ lô vì token. Số tham chiếu đo ở W365, chỉ tính phiên worker: khoảng 2.850 token quota mỗi bài.

Các dấu hiệu kỹ thuật cần xử lý ngay:

| Dấu hiệu | Nghĩa là gì | Làm gì |
|---|---|---|
| `turns_max > 1` | Worker không xong trong một bước, nó đã sa vào viết chương trình | Soi lại phần đầu persona: đoạn tuyên bố không có tool phải đứng trước và phải rõ |
| `reasoning > 0` | Chế độ suy luận chưa tắt, đang tính tiền theo giá đầu ra | Đặt `reasoningEffort: "off"` cho row worker — **phải có dấu nháy**, vì YAML đọc `off` trần thành boolean `false` chứ không thành chuỗi |
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
| Sổ cái báo con số vô lý | Dòng sổ cái ghi không có `--workers-only` nên gộp cả phiên điều phối | `--finish` đã tự truyền cờ này từ 23/09. Dòng cũ hơn thì đọc với dè dặt |
| `DB không ghi được … readonly` | Sandbox workspace-write chặn ghi ra `C:\data\news-scape`; không cấu hình nào mở rộng được | Chạy lại đúng lệnh khung ❌ in ra, với `danger-full-access`. Kiểm bằng `article_run.py --where` |
| Chương trình điều phối trả `stopped` | Đọc packet hỏng; chưa lượt gọi mô hình nào chạy | Báo nguyên văn `failed[].why`. Không sửa tay tệp `.ts`: lỗi phải vá ở `conductor_program()` trong `article_run.py` |
| Bài có bản ghi mà nhận diện bị loại `no l1_task` | Bài đi thẳng từ Article Lane chưa từng qua định tuyến L1 | Đã vá 23/09: `L1Runner` tự ghi dòng `l1_tasks` với `route=article_lane`. Còn gặp thì bài không tồn tại trong `articles` |

---

## 5. Lane L1/Gold cũ đã ngừng

W365 (21/09) là chu kỳ vận hành đầy đủ đầu tiên chạy sạch trên Article Lane, nên lane cũ ngừng hẳn từ 23/09. Radar và bàn giao không còn đọc hay khuyến nghị gì thuộc lane cũ. Không gọi `agent_l1`, `agent_gold`, `l1_route.py`, `l1_ingest.py --code-first` hay `requeue.py`.

Việc dọn dẹp đã làm ngày 23/09 (ADR 0010):

- Gỡ row `agent_l1`/`agent_gold` khỏi preset. `agent_article` là agent con duy nhất.
- Gỡ job `l1_route` + `l1_ingest --code-first` 15 phút khỏi `morninger`. **Tiến trình `morninger` đang chạy phải khởi động lại** thì mới dừng job này.
- Bộ chọn bài không còn coi bản code-first là đã phân tích. 2.915 bài ngày 10–17/09 từng kẹt vì điều này nay quay lại hàng chờ, xem được bằng `radar status --date <ngày>`.
- `--finish` chỉ bung và nạp tệp `article_<mã>_*` của đúng đợt. Dòng `ingested: done/failed` giờ là số của đợt.
- Tệp tồn đã chuyển (không xoá) sang `data/archive/legacy-lane-20260923/`, kèm `MANIFEST.json` ghi cách hoàn tác: 411 packet `agent_tasks/l1/`, 11 tệp `l1_batch_*`, 21 tệp `batch_*` và manifest Gold cũ.

Các dòng `l1_tasks` cũ trong DB được giữ làm lịch sử. Radar và bàn giao không đọc bảng này.
