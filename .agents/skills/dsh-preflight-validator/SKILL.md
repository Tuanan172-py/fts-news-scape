---
name: dsh-preflight-validator
description: Cổng nghiệm thu hạ tầng trước khi chạy agent trên DSH — kiểm 12 hạng mục checklist trong một lệnh, phân định rõ việc Conductor tự làm được và việc người vận hành bắt buộc phải làm tay (restart host, chọn preset, mở phiên), chặn đợt khi có mục ĐỎ.
---

# DSH Preflight Validator — Nghiệm thu hạ tầng trước khi kích hoạt agent

> **Mục tiêu cốt lõi:** Trả lời dứt khoát câu hỏi *"Hạ tầng đã đủ điều kiện để gõ lệnh đợt chưa?"* bằng **số đo**, không bằng cảm nhận. Mọi hạng mục hoặc có lệnh kiểm chứng, hoặc bị coi là chưa đạt.

---

## 0. Vì sao có skill này

Preset DSH được **nạp lúc mount**, không phải lúc sửa tệp. Ngày 18/09 host `dsh web` khởi động lúc 17:46; `agent.cordis.yml` được sửa lúc 21/09 13:43 — nghĩa là **toàn bộ đợt tối ưu bộ nhớ đệm chưa từng có hiệu lực** trong khi mọi dấu hiệu bề mặt đều xanh. YAML đúng, prefix đúng, junction đúng, nhưng runtime vẫn chạy bản cũ.

Sửa tệp xong mà không restart là **trạng thái hỏng im lặng**: không lỗi, không cảnh báo, chỉ có hoá đơn sai. Skill này tồn tại để biến nó thành lỗi ồn ào.

Chính repo đã ghi cơ chế: `.agents/dsh/README.md:32` — *"Dừng host `dsh web` trước. Sửa khi host đang chạy gây live-reload phá tool catalog."*

---

## 1. Bất biến nghiệp vụ

1. **Không tin YAML, tin runtime.** Khoá YAML gõ sai bị **bỏ qua im lặng**. Mọi khẳng định về cấu hình phải kiểm bằng tập tool hiệu lực và `sdkSchemas`, không bằng cách đọc tệp.
2. **Thời điểm mount là chân lý.** So `StartTime` của tiến trình giữ cổng 3080 với `LastWriteTime` của preset. Tệp mới hơn tiến trình ⇒ **bản sửa chưa có hiệu lực**.
3. **Ranh giới quyền được đo, không được đoán.** Trước khi khai một việc là "người phải làm", phải chứng minh Conductor không làm được.
4. **Không có mục XÁM.** Mỗi hạng mục là ĐỎ hoặc XANH. "Chắc là được" tính là ĐỎ.
5. **ĐỎ chặn đợt.** Không có ngoại lệ "chạy tạm rồi sửa sau" — vì triệu chứng duy nhất của lỗi cache là hoá đơn, phát hiện sau khi đã tiêu tiền.
6. **Cổng này 0 token.** Toàn bộ kiểm tra chạy bằng `pwsh` + `read`, không gọi mô hình.

---

## 2. Ranh giới năng lực (đã kiểm chứng bằng probe)

### 2.1 Conductor TỰ LÀM được

| Việc | Bằng chứng |
|---|---|
| Đọc/ghi trong repo | `write` OK dưới `danger-full-access` |
| **Ghi vào `%USERPROFILE%\.dsh\`** | Probe tạo + xoá `_conductor_probe.tmp` thành công |
| Đọc `~\.dsh\settings.yaml` | Đọc được, 16 dòng |
| Chạy mọi script dự án qua `pwsh` | `health`, `radar token`, `--check-prefix`, `--where` |
| Kiểm junction preset | `(Get-Item $p).Target` |
| Kiểm tiến trình + cổng | `Get-CimInstance`, `Get-NetTCPConnection` |
| Sửa `agent.cordis.yml`, `preset.yml`, tài liệu | trong repo |
| Chạy `requeue.py --apply`, sửa DB | |

**Ranh giới thật:** Conductor không bị chặn bởi *quyền ghi*. Nó bị chặn bởi **vòng đời tiến trình** — nó là khách bên trong host, không phải chủ của host.

### 2.2 Chỉ NGƯỜI VẬN HÀNH làm được

| # | Việc | Vì sao Conductor không làm được |
|:-:|---|---|
| 1 | **Restart host `dsh web`** | Conductor chạy *bên trong* tiến trình đó. Kill nó = tự sát giữa lượt. Không có cơ chế tự mọc lại. |
| 2 | **Chọn preset lúc mở phiên** | Xảy ra ở tầng UI, **trước** khi Conductor tồn tại trong phiên. |
| 3 | **Mở phiên mới** | Mọi phiên đều có cha là host. |
| 4 | **Đổi permission preset của phiên** | `permission.defaultPreset` là cấu hình giao diện. |
| 5 | **Duyệt/từ chối prompt** | Approval có thể đang tắt ⇒ bị từ chối tự động. |
| 6 | **Nâng cấp DSH** (`npx`) | Ghi đè chính checkout đang chạy. |
| 7 | **Đổi junction** | Cần quyền; và chỉ có hiệu lực từ lần mount sau. |
| 8 | **Bật `dev:web` (Vite watcher)** | Cần tiến trình nền sống ngoài phiên. |

**Hệ quả của #8:** nếu không có tiến trình vite nào đang chạy thì **HMR client-plugin KHÔNG hoạt động**. Đừng trông vào tự-reload cho bất kỳ thay đổi nào.

---

## 3. Checklist 12 hạng mục

Chạy **toàn bộ** trong **một** lệnh `run_code`. Không tách bước — mỗi bước gửi lại toàn bộ lịch sử.

### Nhóm A — Định danh preset (chặn cứng)

| # | Hạng mục | Cách kiểm | ĐẠT khi |
|:-:|---|---|---|
| A1 | Junction preset sống | `(Get-Item "$env:USERPROFILE\.dsh\.agent-presets\news-scape-conductor").Target` | Trỏ đúng `.agents\dsh\presets\news-scape-conductor` trong repo |
| A2 | Preset mặc định đúng | `settings.yaml` → `agent-presets.default` | `news-scape-conductor` |
| A3 | **Preset đã nạp lại sau lần sửa cuối** | So `(Get-Process -Id <pid3080>).StartTime` với `LastWriteTime` của `agent.cordis.yml` | **StartTime > mtime preset** |
| A4 | Phiên đúng preset | Tập tool trực tiếp chỉ có `run_code`; SDK có `pwsh`, `read`, `write`, `agent_article` | Đủ cả hai vế |

> **A3 là hạng mục quan trọng nhất và hay bị bỏ nhất.** Máy không tự biết "đã restart chưa" — phải suy từ hai mốc thời gian.

### Nhóm B — Bộ nhớ đệm tiền tố

| # | Hạng mục | Cách kiểm | ĐẠT khi |
|:-:|---|---|---|
| B1 | Prefix khớp catalog | `article_run.py --check-prefix` | exit 0 |
| B2 | Persona trong preset khớp prefix | `build_article_prefix.py --check-preset` | exit 0 |

> **B1 khác B2.** `--check` kiểm **hai** vế (tệp ↔ catalog, persona ↔ tệp). `--check-preset` chỉ kiểm vế thứ hai, dùng ngay sau khi dán tay. Dùng `--check` làm cổng trước đợt.

### Nhóm C — Hợp đồng runtime

| # | Hạng mục | Cách kiểm | ĐẠT khi |
|:-:|---|---|---|
| C1 | `reasoningEffort` tắt | `settings.yaml` → `agent-default-model.reasoningEffort` | `off` |
| C2 | Permission đủ ghi | `permission.defaultPreset` | `workspace-write` cho đợt thật |
| C3 | `mode: ptc` nguyên vẹn | `grep "mode: ptc"` trong preset | Có mặt — đổi sang `native` là phá kiến trúc |
| C4 | Không có Vite watcher | Xem §5.1 `C4`. **Phải loại trừ chính tiến trình của Conductor** | Không có vite thật ⇒ **đừng trông vào HMR** (thông tin, không chặn) |

### Nhóm D — Sẵn sàng dữ liệu

| # | Hạng mục | Cách kiểm | ĐẠT khi |
|:-:|---|---|---|
| D1 | Script đường article đủ | Glob 13 script bắt buộc | Đủ 13/13 |
| D2 | Task `failed` đã requeue | `pipeline_radar.py status` | Không còn 🔴 failed tồn |
| D3 | Ngày dữ liệu khớp `--today` | Đối chiếu radar với liveness scraper | Cùng một ngày |
| D4 | Áp suất ngữ cảnh | `ctx_probe.py` | 🟢 <25% |

---

## 4. Quy trình thực thi

```text
[Bắt đầu phiên mới]
       │
       ▼
[Bước 1] Chạy checklist 12 mục trong MỘT run_code (0 token)
       │
       ├── Có mục ĐỎ ở nhóm A (A1–A4)?
       │        │
       │        ├── A1/A2 sai  ──► Conductor sửa được (junction/settings.yaml)
       │        │                 └─► nhưng hiệu lực chỉ sau RESTART
       │        ├── A3 sai     ──► 🔴 DỪNG. Người vận hành PHẢI restart host.
       │        │                 Không có đường vòng. Báo rõ 2 mốc thời gian.
       │        └── A4 sai     ──► 🔴 DỪNG. Người vận hành PHẢI mở lại phiên
       │                          với preset News-Scape Conductor.
       │
       ├── Có mục ĐỎ ở nhóm B?
       │        └──► Conductor TỰ sửa: build_article_prefix.py
       │             → dán persona vào preset → --check-preset
       │             → RỒI QUAY LẠI A3 (cần restart nữa)
       │
       ├── Có mục ĐỎ ở nhóm C?
       │        ├── C1 sai ──► người sửa settings.yaml, cần restart
       │        ├── C2 sai ──► người đổi permission preset của phiên
       │        └── C3 sai ──► 🔴 DỪNG NGAY. Sửa code, không được chạy.
       │
       └── Có mục ĐỎ ở nhóm D?
                ├── D2 ──► Conductor TỰ chạy requeue --apply
                ├── D3 ──► Conductor báo cáo, người quyết chạy ngày nào
                └── D4 ──► 🟡 đóng phiên, mở phiên mới

[Tất cả XANH] ──► Đủ điều kiện gõ lệnh đợt
```

### Điểm quay lui bắt buộc

Sửa preset (B2) **luôn** kéo theo nhu cầu restart (A3). Sau khi dán persona, **phải quay lại kiểm A3** trước khi kết luận XANH. Bỏ bước này là bỏ đúng bước quan trọng nhất.

---

## 5. Mẫu lệnh

### 5.1 Checklist gộp — một `run_code`

Xem khối mã bên dưới. Nguyên tắc: gom mọi lệnh kiểm vào **một** chương trình, chỉ `return` các phán quyết ĐỎ/XANH, không trả nội dung thô.

```ts
const PY = 'C:\\venvs\\news-scape\\Scripts\\python.exe';
const WD = 'C:\\Users\\anpt\\OneDrive - fpts.com.vn\\FRA_DataIngestion - news-scape\\project';
const PRESET = WD.replace(/\\project$/, '') +
  '\\.agents\\dsh\\presets\\news-scape-conductor\\agent.cordis.yml';

async function sh(label, command, workdir) {
  const r = await tools.pwsh({ command, description: label, ...(workdir ? { workdir } : {}) });
  return r.kind === 'foreground'
    ? { code: r.exitCode, out: (r.stdout.text + r.stderr.text).trim() }
    : { code: null, out: '(background)' };
}

const res = {};

// A1 + A2 + C1 + C2 — định danh và hợp đồng runtime
res.identity = await sh('identity', [
  '$j = "$env:USERPROFILE\\.dsh\\.agent-presets\\news-scape-conductor"',
  'if (Test-Path $j) { "junction -> " + (Get-Item $j).Target } else { "JUNCTION MISSING" }',
  '"--- settings ---"',
  'Get-Content "$env:USERPROFILE\\.dsh\\settings.yaml" | Select-String "default:|reasoningEffort|defaultPreset"'
].join('; '));

// A3 — hạng mục then chốt: preset đã được nạp lại chưa
res.mount = await sh('A3 mount-vs-mtime', [
  '$p = (Get-NetTCPConnection -LocalPort 3080 -State Listen -ErrorAction SilentlyContinue).OwningProcess',
  'if (-not $p) { "NO SERVER ON 3080"; exit 1 }',
  '$st = (Get-Process -Id $p).StartTime',
  '$mt = (Get-Item "' + PRESET + '").LastWriteTime',
  '"server StartTime : $st"',
  '"preset mtime     : $mt"',
  'if ($st -gt $mt) { "A3 VERDICT: OK" } else { "A3 VERDICT: STALE — PHAI RESTART" }'
].join('; '));

// C3 — bất biến kiến trúc
res.ptc = await sh('C3 ptc', 'Select-String -Path "' + PRESET +
  '" -Pattern "mode: ptc","maxDepth:" | ForEach-Object { $_.Line.Trim() }');

// C4 — có watcher không.
// CANH BÁO: Conductor tự chạy như một node subprocess ("dsh-subprocess-local"),
// và chính tiến trình đó khớp regex "dev:web" nếu không loại trừ. Bản đầu của
// skill này trả về 1 vì bắt nhầm chính nó. Phải trừ cả hai họ tiến trình của DSH.
res.watcher = await sh('C4 watcher', [
  'Get-CimInstance Win32_Process -Filter "Name=\'node.exe\'"',
  '| Where-Object { $_.CommandLine -match "vite|dev:web" }',
  '| Where-Object { $_.CommandLine -notmatch "dsh-subprocess-local|@deepseek-ai.dsh|dsh-code-runtime" }',
  '| ForEach-Object { "WATCHER PID {0}" -f $_.ProcessId }',
  '| Measure-Object | Select-Object -ExpandProperty Count'
].join(' '));

// B1 — cổng prefix (kiểm cả hai vế)
res.prefix = await sh('B1 check-prefix', '& "' + PY + '" scripts/article_run.py --check-prefix', WD);

// D1 — script đủ chưa
res.scripts = await sh('D1 scripts', [
  '$need = @("article_run.py","article_pack.py","article_expand.py","build_article_prefix.py",',
  '"pipeline_radar.py","ctx_probe.py","token_ledger.py","write_user_output.py","handoff.py",',
  '"l1_ingest.py","agent_ingest.py","estimate_wave.py","run_once.py")',
  '| ForEach-Object { $_ };',
  '$miss = $need | Where-Object { -not (Test-Path ("scripts/" + $_)) };',
  'if ($miss) { "MISSING: " + ($miss -join ", ") } else { "OK 13/13" }'
].join(' '), WD);

// D4 — áp suất ngữ cảnh
res.ctx = await sh('D4 ctx_probe', '& "' + PY + '" scripts/ctx_probe.py', WD);

return res;
```

### 5.2 Chỉ kiểm hạng mục then chốt A3 (khi nghi ngờ)

```powershell
$p = (Get-NetTCPConnection -LocalPort 3080 -State Listen).OwningProcess
"server : " + (Get-Process -Id $p).StartTime
"preset : " + (Get-Item ".agents\dsh\presets\news-scape-conductor\agent.cordis.yml").LastWriteTime
```

**Đạt khi:** dòng `server` **mới hơn** dòng `preset`.

---

## 6. Trình tự restart (việc của người vận hành)

1. Sửa xong preset / `settings.yaml`.
2. **Dừng host:** `Ctrl+C` ở cửa sổ đang chạy `npx @deepseek-ai/dsh web`.
3. **Khởi động lại:** `npx @deepseek-ai/dsh web`.
4. Mở GUI `http://127.0.0.1:3080`, chọn preset **News-Scape Conductor**, tạo phiên mới quyền **`workspace-write`**.
5. Nghiệm thu bằng A3 + A4.

> **Không có cách nào để Conductor tự làm bước 2–4.** Đây không phải giới hạn quyền mà là giới hạn vòng đời tiến trình.

---

## 7. Xử lý sự cố

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| Mọi thứ xanh nhưng hoá đơn sai | Preset mới hơn tiến trình (A3 ĐỎ) | Restart host |
| `agent_article` không có trong SDK | Phiên sai preset (A4) | Mở lại phiên đúng preset. Đây là nguyên nhân gốc vệt 845K ngày 17/09 |
| Junction mất | Đổi máy / di chuyển OneDrive / clone mới | `mklink /J` theo `RUNBOOK-article-lane.md` |
| Sửa `settings.yaml` không có tác dụng | Khoá YAML sai bị bỏ qua im lặng | Khẳng định tập tool hiệu lực + `sdkSchemas` ở runtime, **không tin YAML** |
| Client-plugin không tự reload | Không có Vite `dev:web` | Bật watcher, hoặc refresh thủ công |
| **C4 báo có watcher nhưng thực ra không có** | Regex `vite\|dev:web` bắt nhầm tiến trình `dsh-subprocess-local` của chính Conductor | Đã vá ở §5.1: loại trừ `dsh-subprocess-local`, `@deepseek-ai.dsh`, `dsh-code-runtime` |
| `health` exit 1 | Profile scraper cũ còn sót trong DB | `maintenance/clean_onedrive_conflicts.py` |

---

## 8. Neo tham chiếu

- `.agents/dsh/RUNBOOK.md` §0 (preflight 3 việc) · §5 (hai chốt tự động) · §7 (sự cố) · §8 (bất biến)
- `.agents/dsh/RUNBOOK-article-lane.md` §0 (chuẩn bị một lần)
- `.agents/dsh/DSH-VIEC-THU-CONG.md` — việc chỉ làm được bằng tay
- `.agents/dsh/README.md:32,42` — cảnh báo live-reload khi host đang chạy
- `plans/20260918-1651-article-lane-unified/plan.md` §3, §8

> **Cảnh báo về tài liệu:** `DSH-VIEC-THU-CONG.md` mục 2 và 7 viện dẫn `.dsh/settings.yaml` khai `ptc` và `high`. Kiểm ngày 21/09 cho thấy **cả hai đều sai** — tệp không tồn tại trong repo, còn `%USERPROFILE%\.dsh\settings.yaml` khai `news-scape-conductor` và `off`. Đừng tin tài liệu, tin lệnh kiểm.
