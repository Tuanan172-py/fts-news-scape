# ĐỢT W365 — Bàn giao sang phiên khác

|  |  |
| --- | --- |
| Đóng gói lúc | 2026-09-21 17:35:31 |
| Ngày dữ liệu | **2026-09-21** (ghim bằng `--date`, không dùng `--today`) |
| Số bài | **365** |
| Số lô | **4** |
| Trạng thái | ✅ Đã đóng gói xong · **chưa tiêu token nào** |
| Prefix | `hash=b1c3226cc3107d5d` · persona khớp `19.029` ký tự |

> **Một đợt = một mục tiêu = một phiên.** Đợt này đã đóng gói sẵn. Phiên đóng gói **không** chạy nó — mở phiên mới và dán một lệnh duy nhất.

---

## 0. Vì sao phải sang phiên khác

Chi phí phiên điều phối tỉ lệ với **bình phương số bước**, không theo số bài. Phiên đóng gói đã tích luỹ ngữ cảnh kiểm tra hạ tầng; chạy 4 lô trong đó là trả tiền cho toàn bộ lịch sử ấy ở mỗi bước.

Phiên mới = ngữ cảnh rỗng + **bộ nhớ đệm vẫn còn** (cache nằm phía nhà cung cấp, không gắn với phiên). Đây là lý do đóng phiên là thao tác bình thường, không phải chữa cháy.

---

## 1. Thao tác thiết lập trước khi mở phiên — **bắt buộc**

### 1.1 Xác nhận host còn bản preset mới

**Chạy từ gốc repo.** Đường dẫn bên dưới là tương đối, nên đứng sai thư mục sẽ báo `PathNotFound`:

```powershell
cd "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape"

$p = (Get-NetTCPConnection -LocalPort 3080 -State Listen).OwningProcess
"server : " + (Get-Process -Id $p).StartTime
"preset : " + (Get-Item ".agents\dsh\presets\news-scape-conductor\agent.cordis.yml").LastWriteTime
```

Bản không phụ thuộc thư mục (dán được từ bất kỳ đâu):

```powershell
$R = "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape"
$p = (Get-NetTCPConnection -LocalPort 3080 -State Listen).OwningProcess
"server : " + (Get-Process -Id $p).StartTime
"preset : " + (Get-Item "$R\.agents\dsh\presets\news-scape-conductor\agent.cordis.yml").LastWriteTime
```

**Đạt khi dòng `server` mới hơn dòng `preset`.** Đo lúc đóng gói: `server = 09/21/2026 17:28:21`, `preset = 09/21/2026 13:43:12` → ✅ đạt.

> Nếu bạn **không** sửa gì thêm thì không cần restart. Chỉ restart khi đã chạm vào `agent.cordis.yml` hoặc `settings.yaml`.

### 1.2 Mở phiên mới đúng preset

Settings → General → Agent preset → **News-Scape Conductor**.

Sau đó tạo phiên mới với quyền **`workspace-write`** (cần để ghi output và nạp DB).

**Chọn preset TRƯỚC khi gửi tin đầu tiên.** Preset nạp lúc mount; đổi sau khi phiên đã mở không có tác dụng.

---

## 2. Prompt mồi — dán nguyên văn vào phiên mới

```text
Chạy đợt W365 đã đóng gói sẵn.

Đọc .agents/dsh/DSH-WAVE-W365-HANDOFF.md và làm theo đúng §3 và §4 trong đó.
Không hỏi lại, không đề nghị xác nhận — lệnh đợt đã được gõ tường minh.

Tóm tắt việc phải làm:
1. Dán TRỌN nội dung project/data/agent_tasks/article/wave_W365.conductor.ts
   vào MỘT lệnh run_code. Không tách thành nhiều bước. Không in nội dung packet
   hay output của lô.
2. Chạy article_run.py --wave W365 --finish
3. Chạy write_user_output.py --date 2026-09-21
4. Báo cáo: số lô thành công/thất bại, token mỗi bài, áp suất ngữ cảnh,
   và bốn dấu hiệu bất thường (turns_max, reasoning, token/bài, áp suất).
```

### Prompt mồi tối thiểu (nếu không muốn trỏ tệp)

```text
Chạy đợt W365: dán trọn project/data/agent_tasks/article/wave_W365.conductor.ts
vào MỘT lệnh run_code, rồi chạy article_run.py --wave W365 --finish và
write_user_output.py --date 2026-09-21. Không hỏi lại.
```

---

## 3. Bốn lô đã đóng gói

| Lô | Bài | Tier 1 | Cửa sổ đọc | Đỉnh ngữ cảnh dự toán |
| --- | --: | --: | --: | --: |
| `article_W365_01` | 92 | 92 | 13 | 229.989 |
| `article_W365_02` | 91 | 91 | 13 | 230.627 |
| `article_W365_03` | 91 | 26 | 14 | 244.319 |
| `article_W365_04` | 91 | 0 | 13 | 230.670 |

**Đỉnh ngữ cảnh lớn nhất: 244.319 token (24,4% cửa sổ 1M).** Dưới ngưỡng chia nhỏ 25%, nên `article_pack.py` giữ nguyên 4 lô — không tự chia thêm.

### Artefact trên đĩa

```text
project/data/agent_tasks/article/
  wave_W365.json               manifest — nguồn chân lý của đợt
  wave_W365.conductor.ts       chương trình phải dán vào run_code
  article_W365_01.task.json    546 KB
  article_W365_01.map.json     chỉ số i -> article_id
  article_W365_02.task.json    551 KB
  article_W365_02.map.json
  article_W365_03.task.json    610 KB
  article_W365_03.map.json
  article_W365_04.task.json    554 KB
  article_W365_04.map.json
```

---

## 4. Trình tự chạy — 3 bước

### Bước 1 — chạy mô hình (1 bước, TIÊU TOKEN)

Dán **trọn** `wave_W365.conductor.ts` vào **một** lệnh `run_code`.

Chương trình tự làm: hâm bộ nhớ đệm bằng packet tí hon → đọc 4 packet theo cửa sổ dòng đã tính sẵn → chạy 4 lô song song (`CONCURRENCY = 4`) → ghi thẳng ra `data/agent_outputs_article/<batch_id>.output.json` → chỉ trả về vài con số.

**Đừng tách.** Đừng đọc packet ở bước này rồi gọi agent ở bước khác.

### Bước 2 — hoàn tất (0 token)

```powershell
cd "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape\project"
& "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave W365 --finish
```

Chuỗi: `article_expand.py` → (rc=1 ⇒ **dừng, không nạp DB**) → `agent_ingest.py` → `token_ledger.py append` → `handoff.py` → `ctx_probe.py`.

**Kiểm thiếu bài trước khi finish (khuyến nghị):**

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave W365 --repair
```

Ba trạng thái: chưa có output (exit 2) · đủ bài (không cần vá) · thiếu bài → sinh `wave_W365.repair.ts`, chạy trọn trong một `run_code` rồi mới finish.

### Bước 3 — giao hàng (0 token)

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --date 2026-09-21
```

Ghi vào **gốc kho**, không nằm trong `project/`:
`users\output\<user>\2026-09-21.xlsx`
Users đang bật: `AnPT, PhoHG, ThanhTD, UyenNNT, VyPTT`

---

## 5. Dự toán chi phí

| Rổ | Token |
| --- | --: |
| Đầu vào mới (miss) | 562.533 |
| Đầu vào tái dùng (hit) | 44.572 |
| Đầu ra | 328.500 |
| **Quota dự toán** | **946.748** |

⚠️ **Dự toán này đang lệch +273% so với thực tế** — đo trên đợt W1 ngày 18/09 (dự toán 87.007 miss, thật 324.554). Coi con số trên là **sàn**, không phải trần.

Tham chiếu sổ cái thật (100 bài, 18/09): `quota 1.154.498 · $0,1142 · 11.545 token/bài`.

**Cửa sổ giá:** peak = 08:00–11:00 và 13:00–17:00, T2–T6. Đóng gói lúc 17:35 — **sau 17:00 là off-peak, rẻ 50%**. Chạy ngay bây giờ là đúng cửa sổ.

---

## 6. Sau khi chạy — đọc số

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token --wave W365
& "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py report --wave W365
& "C:\venvs\news-scape\Scripts\python.exe" scripts/ctx_probe.py
```

### Bốn dấu hiệu phải báo ngay nếu thấy

| Dấu hiệu | Nghĩa |
| --- | --- |
| `turns_max > 1` | Worker sa vào viết chương trình thay vì trả lời thẳng. Persona cần sửa |
| `reasoning > 0` | Chế độ suy luận chưa tắt, đang tính tiền theo giá đầu ra |
| token/bài > 1.500 | Mốc quy kết gộp nhầm phiên khác, hoặc packet quá dày |
| áp suất vàng/đỏ | Xong đợt thì **đóng phiên**, mở phiên mới rẻ hơn |

---

## 7. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Xử lý |
| --- | --- | --- |
| `--finish` báo "chưa có đầu ra nào" | Chương trình PTC chưa chạy hoặc ghi sai thư mục | Chạy bước 1; kiểm `data/agent_outputs_article/` |
| Thiếu bài trong lô | Lô dài, output bị cắt | `--wave W365 --repair` — đóng gói lại đúng phần thiếu |
| `parse_fail` > 10% | Worker trả kèm lời dẫn | `--finish` dừng trước khi nạp DB. Xem lại persona, chạy lại đúng lô hỏng |
| Không thấy `agent_article` trong SDK | Phiên sai preset | Mở lại phiên đúng **News-Scape Conductor** |
| Prefix lệch giữa hai lô | Đổi tool set/model/effort giữa phiên | Không đổi gì trong phiên; đổi giữa hai đợt |
| `Get-Item : Cannot find path 'C:\Users\anpt\.agents\...'` | Đang đứng ở `C:\Users\anpt` chứ không phải gốc repo; đường dẫn tương đối ghép sai gốc | `cd` vào gốc repo, hoặc dùng bản đường dẫn tuyệt đối ở §1.1 |

---

## 8. Bất biến không được vi phạm

1. **Conductor bắt buộc `mode: ptc`.** Đổi sang `native` là output con rơi vào ngữ cảnh cha.
2. **Một đợt = ít bước nhất có thể.** Bước 1 là **một** lệnh `run_code` cho cả 4 lô.
3. **Không để nội dung lô vào ngữ cảnh.** Chỉ `print`/`return` mới vào lịch sử; kết quả ghi thẳng ra đĩa.
4. **Không đọc lại tệp vừa ghi.** Việc kiểm định thuộc về cổng nghiệm thu ngoài.
5. **Không tự làm việc của script.** Việc nào kiểm được bằng mã thì script làm.

---

## 9. Đợt này KHÔNG bao gồm

Đóng gói 365 bài — **toàn bộ** bài đăng ngày 21/09, không lọc theo watchlist. Cần biết trước:

- Chỉ **37/365 bài** có `symbols` (mã cổ phiếu) — phần lớn là tin vĩ mô/thị trường chung.
- Radar báo `Gold đủ điều kiện Subscriber-Gated: 0 bài` trước khi chạy.
- Đợt này **không** xử lý: 4 `work_items` trạng thái `held`, 441 batch L1 tồn đọng đường cũ, 2 batch Gold từ 17/09.

Nếu mục tiêu là phủ 100% kho dữ liệu hôm nay thì đợt này đúng. Nếu mục tiêu là tiết kiệm token thì nên lọc watchlist trước khi đóng gói.

---

*Neo: `.agents/dsh/RUNBOOK-article-lane.md` · `.agents/dsh/RUNBOOK.md` · skill `dsh-conductor` · skill `dsh-preflight-validator`*
