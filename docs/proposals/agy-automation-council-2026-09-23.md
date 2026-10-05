# Đề xuất: Tự động hoá Article Lane bằng Antigravity CLI (`agy`) — kết luận hội đồng 2026-09-23

|                  |                                                                                                                                         |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Loại tài liệu | **Đề xuất (proposal)**, chưa phải quyết định. Cần Intake #25 → ADR 0010 → Human duyệt trước khi sửa mã sản xuất |
| Tier             | **Cấp 3 HIGH-RISK** (AGENTS.md §0: chạm automation substrate + provider mới) — tiền lệ ADR 0009                            |
| Phạm vi         | Thêm runner`agy` **song song** DSH cho stage cognitive duy nhất `article_analyze`. DSH giữ mặc định                     |
| Bằng chứng     | `docs/proposals/agy-council-2026-09-23/` (dossier, 3 position paper, 3 rebuttal, 2 file kết quả spike)                              |
| agy              | 1.2.7 →**1.2.9 tự cập nhật trong lúc thẩm định** (bằng chứng cho việc phải ghim phiên bản)                          |
| Nhãn            | **[V]** kiểm chứng thực nghiệm tại máy · **[S]** có nguồn · **[I]** suy luận                               |

## 0. Tóm tắt một đoạn

Phương án thắng: **Python là conductor, `agy` là hàm nhận thức thuần (một tiến trình / một batch / một lượt, không tool)**, chạy trong **hồ sơ worker cô lập** với **custom agent toàn cục** mang nguyên văn `ARTICLE_SYSTEM_CORE.md`, dữ liệu vào qua **stdin `stream-json`**, đầu ra là text JSON được **Python parse + validate** (không dùng `--json-schema`). Kích hoạt bằng **một Task Scheduler tick** có khoá, kill-switch, standing order, quota guard; tự chủ theo **thang L0 → L1 → L2**. Các phương án MCP pull-worker, sidecar/agentapi, remote-control, workspace-agent, stdin text-mode đều **bị loại có bằng chứng**.

## 1. Quy trình hội đồng

| Vòng                                        | Thành phần                                                                                                                               | Kết quả                                     |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------- |
| 1 — Nghiên cứu                            | A: sự thật agy (web + 11 lệnh thử) · B: pipeline & governance repo · C: trigger/subprocess Windows · D: tính năng native của agy | `dossier_round1.md`                         |
| 2 — Lập trường + spike                   | D1 hàm thuần (8 lệnh agy) · D2 agy-native MCP/hook (8 lệnh) · D3 vận hành & governance red team                                    | `position_1..3.md`, `spike1/2-RESULTS.md` |
| 3 — Phản biện chéo + spike quyết định | D2 thử custom agent trong hồ sơ worker (5 lệnh); D1, D3 phản biện                                                                    | `rebuttal_1..3.md`                          |

## 2. Sự thật chịu lực (đã kiểm chứng)

| #   | Sự thật                                                                                                                                                                                                                                                                                                                                                                  | Hệ quả thiết kế                                                                                                                                                                                                                                                                                     |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1  | `agy -p` **bỏ qua stdin ở text mode** [V]. `--input-format stream-json` (NDJSON `{"event":"user","message":{"content":"..."}}`) hoạt động, UTF-8 tiếng Việt nguyên vẹn [V]                                                                                                                                                                            | Payload đi qua stdin stream-json. Bác bỏ đề xuất`--input-format text` của bản nháp                                                                                                                                                                                                           |
| F2  | argv Windows trần 32.767 (thử: 32.000 OK, 32.800 → WinError 206); cmd.exe 8.191 [V]                                                                                                                                                                                                                                                                                     | Không bao giờ nhét bài vào`-p`                                                                                                                                                                                                                                                                   |
| F3  | **Thành công giả**: tool bị từ chối → exit 0, `SUCCESS`, `response:""` + `denied_actions`; hết `--print-timeout` → exit 0, usage = 0, chỉ stderr báo [V]. Lỗi API → exit 3 + `AGY_ERROR:{retryable}` [S changelog]                                                                                                                            | Bộ phân loại lỗi không được tin exit code                                                                                                                                                                                                                                                       |
| F4  | Mặc định agy mang ~11,7k token system prompt + 57 tool mỗi lần gọi;`cache_read` **= 0 giữa các tiến trình** kể cả prefix gần giống hệt [V]                                                                                                                                                                                                          | Không tính cache vào ngân sách                                                                                                                                                                                                                                                                     |
| F5  | Workspace agent (`.agents/agents/*.md`) **không nạp**, agy **lặng lẽ fallback** agent mặc định, exit 0; sự kiện `init` vẫn ghi tên agent [V]                                                                                                                                                                                                    | Kiểm tra nạp agent bằng`cli.log`, không bằng `init`. Nguyên nhân [I]: workspace chưa được trust đúng đường dẫn (log `loaded 0 named hooks from 0 hooks.json`), không phải sai bố cục thư mục — đã có đường thay thế đã kiểm chứng (F7) nên không theo đuổi |
| F6  | Trỏ`USERPROFILE`/`HOME`/`ANTIGRAVITY_APP_DATA_DIR` sang **hồ sơ worker riêng** → agy chỉ nạp allowlist/hook/agent của hồ sơ đó; đăng nhập vẫn qua keyring [V]                                                                                                                                                                                  | Cô lập khỏi allowlist toàn cục đang có`command(regex:.*\.py$)` — thay thế `--dangerously-skip-permissions`                                                                                                                                                                                 |
| F7  | **Custom agent toàn cục trong hồ sơ worker nạp được** (`agent=true` trong log), `excludeDefaultComponents: true`, `tools: []`, body = CORE: input **24,9k → 13,6k (−45%)**, 1 lượt, 5/5 bản ghi đúng thứ tự, **0 mã nhóm sai** (baseline 15% sai), bỏ qua lời dụ `view_file` [V]                                           | Đây là cấu hình chuẩn                                                                                                                                                                                                                                                                             |
| F8  | `--json-schema` được agy hiện thực bằng tool ẩn `finish` → xung đột `tools: []` (vòng lặp 4 lượt, ×2,4–3,6 token, không có `structured_output`); mảng cấp cao nhất và `prefixItems` bị từ chối (400, exit 3) [V]                                                                                                                        | **Không dùng `--json-schema`**. CORE đã yêu cầu "một mảng JSON"; Python parse (`salvage_records`) + jsonschema + kiểm tra miền                                                                                                                                                      |
| F9  | Hook (`PreToolUse/PostToolUse/Stop`) **có chạy trong `-p`**; hook crash = chặn tool (fail-safe); Stop **không** chạy khi kết thúc do từ chối quyền [V]                                                                                                                                                                                           | Hook deny-all là lớp phòng thủ phụ, không phải cơ chế chính                                                                                                                                                                                                                                   |
| F10 | `agentapi`/sidecar cần app Antigravity chạy (`ANTIGRAVITY_LS_ADDRESS is not set`, exit 0) và bật tay trong dashboard; `remote-control` chỉ là UI cho người [V]                                                                                                                                                                                               | Loại khỏi vai trò trigger                                                                                                                                                                                                                                                                            |
| F11 | 3 tiến trình`agy -p` song song chạy tốt [V]; quota dùng chung pool "Work Done" với IDE/tương tác, làm mới 5h + trần tuần [S]                                                                                                                                                                                                                                | Pool 2, quota guard bắt buộc                                                                                                                                                                                                                                                                          |
| F12 | DB thật ở`C:\data\news-scape\monocle.db` qua env `MONOCLE_DB_PATH`; `settings.yaml:3` trỏ bản OneDrive cũ → **split-brain** nếu tác vụ lịch chạy thiếu env [V]; `article_run.py:435-450` `--finish` chạy ingest với `check=False` (nuốt lỗi, trái ADR 0008 §2.4) [V]; `news_cron` đang va chạm `morninger` (OPEN-ITEMS A0-5) [V] | Tiền đề phải sửa trước (US-025)                                                                                                                                                                                                                                                                  |

## 3. Kiến trúc được chọn

```
Task Scheduler "ns_article_tick" (ngày làm việc, 30')   ← trigger duy nhất
        │  (Interactive only — auth qua keyring)
        ▼
article_tick.py  (operator, 0 token)
   1 AGY_STOP? → thoát      2 standing order còn hạn? (L1/L2)   3 .pipeline.lock (Python, C:\data)
   4 assert DB path == MONOCLE_DB_PATH   5 agy --version == pin   6 tái tạo + hash hồ sơ worker & CORE
   7 quota ledger / circuit breaker      8 sự kiện: backlog ≥ 50 HOẶC cửa sổ 07:30 / 15:30 / 17:30 (gom bù)
        ▼
article_run.py --runner agy --wave W     (DSH vẫn là --runner dsh mặc định)
   prepare (article_pack, không đổi) ─► analyze: pool 2 × agy_runner ─► finish (fail-loud) ─► [L2] ingest
                                             │
          ┌──────────────────────────────────┘ mỗi batch một tiến trình mới
          ▼
  env: USERPROFILE=HOME=<worker_home>, ANTIGRAVITY_APP_DATA_DIR=<worker_home>\.gemini\antigravity-cli,
       PYTHONUTF8=1 ; cwd = thư mục rỗng theo wave dưới %LOCALAPPDATA% (ngoài repo, ngoài OneDrive)
  agy -p= --agent article-processor --model <pin> --input-format stream-json --output-format stream-json
      --print-timeout 300s --disable-slash-commands            (không --json-schema, không skip-permissions)
  stdin: 1 dòng NDJSON = "## Packet\n" + nội dung task.json
          ▼
  Python: phân loại → parse → validate miền → ghi nguyên tử <batch>.output.json + <batch>.meta.json → ledger
```

Hồ sơ worker (tái tạo mỗi tick, so hash, vì agy tự ghi đè `settings.json`):

- `.gemini/config/agents/article-processor.md`: frontmatter `tools: []`, `excludeDefaultComponents: true`, `inheritCustomizations: false`; body = byte-identical `ARTICLE_SYSTEM_CORE.md` (ghi `core_sha` vào meta).
- `settings.json` **không** có allow rule nào; tuỳ chọn `hooks.json` PreToolUse deny-all.

### 3.1 Bộ phân loại mỗi lần gọi (thứ tự)

| # | Kiểm tra                                                                                                 | Phân loại → hành động                                                                                                       |
| - | --------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| 1 | exit ≠ 0 /`AGY_ERROR`                                                                                  | 3+retryable → RETRYABLE (backoff full-jitter, tối đa 3) · 429/quota → QUOTA (mở breaker tới mốc 5h) · còn lại → FATAL |
| 2 | stderr "print timeout" hoặc usage = 0                                                                    | TIMEOUT → kill cây tiến trình (Job Object / psutil), chia đôi batch, thử lại 1 lần                                       |
| 3 | `cli.log` thiếu `agent=true` / có `not found, falling back` / input lượt 1 > CORE + packet + 3k | FATAL (agent không nạp — sai cấu hình, dừng lane)                                                                           |
| 4 | model trong`init` ≠ pin                                                                                | FATAL                                                                                                                             |
| 5 | bất kỳ`step_type == tool` hoặc `denied_actions` ≠ ∅                                              | VIOLATION + cảnh báo; 2 lần/wave → dừng wave                                                                                 |
| 6 | > 1 phản hồi model                                                                                      | cảnh báo double-generation                                                                                                      |
| 7 | parse`salvage_records` thất bại                                                                       | SOFT_FAIL → thử lại                                                                                                            |
| 8 | Validate miền (dưới)                                                                                   | bản ghi hỏng → PARTIAL →`--repair`                                                                                          |
| 9 | OK                                                                                                        | `safe_atomic_write` output + meta, dòng `agy_calls` + ledger                                                                 |

### 3.2 Cổng kiểm tra miền trước `--finish` (bổ sung)

Tập `i` trả về khớp đúng packet · `e[1]` ∈ 11 mã (TIC, COM, PER, FND, IDX, EXC, IND, GEO, THM, AST, INS) · `e[0]` xuất hiện nguyên văn trong tiêu đề/đoạn (trừ IND) · `c` trong phạm vi và ≥ 2 chỉ số khác nhau · enum `sn`/`ts` và độ dài `im` · **bài nguồn có dấu mà `s`/`im` mất dấu → loại** (D2 quan sát mô hình bỏ dấu) · `meta.json` tồn tại, `core_sha` khớp, wave chỉ một runner. Tỷ lệ "hỏng" = parse-fail + bị validator loại + trường bị rơi; giữ ngưỡng dừng 10% hiện hành.

### 3.3 Kích thước batch

Chi phí cố định sau custom agent ≈ 8k token (gồm CORE); mỗi bài ≈ 1,1k vào / 0,3k ra [V trên mẫu 5 bài, I cho quy mô lớn].

| N            | Input/lần | Output/lần | Tỷ trọng cố định | Token / 1.000 bài |
| ------------ | ---------- | ----------- | --------------------- | ------------------ |
| 25           | ~36k       | ~7,5k       | ~22%                  | ~1,74M             |
| **50** | ~63k       | ~15k        | ~13%                  | **~1,56M**   |
| 100          | ~118k      | ~30k        | ~7%                   | ~1,48M             |

Khuyến nghị: **mặc định 50 cho agy (DSH giữ 100)**, tự chia đôi khi TIMEOUT/cắt cụt. 100 chỉ tiết kiệm ~5% nhưng nhân đôi thiệt hại khi retry và rủi ro cắt output — chỉ nâng nếu spike B chứng minh không cắt cụt. (D2 đề xuất 25–30 để thu hẹp bán kính tổn thất; hội đồng chọn 50, spike B quyết định cuối.)

### 3.4 Thang tự chủ (hoà giải ADR 0008 "lệnh operator = phê duyệt")

| Mức         | Hành vi                                                                                | Điều kiện lên mức               |
| ------------ | --------------------------------------------------------------------------------------- | ------------------------------------ |
| **L0** | Operator gõ`article_run.py --runner agy --wave W`                                    | A/B đạt (mục 5) + 3 wave L0 sạch |
| **L1** | Tick tự prepare + analyze,**dừng trước nạp DB**; operator chạy `--finish` | Standing order + 5 wave sạch        |
| **L2** | Tự`--finish` + ingest; **giao xlsx vẫn thủ công**                           | —                                   |

Standing order = file do operator tạo, **hết hạn ≤ 7 ngày**, hash ghi vào meta của mỗi wave, tạo/gia hạn sinh trace harness. Đây là "lệnh operator tường minh" dạng có thời hạn — không tái lập cổng xác nhận mà plan đã bỏ. Kill switch `AGY_STOP` kiểm tra trước mỗi batch; L2 tự rơi về L0 sau 2 wave hỏng liên tiếp; cảnh báo dead-man khi 24h không có wave thành công trong lúc backlog ≥ 50; lệch phiên bản agy → lane tối + cảnh báo + runbook ghim lại.

### 3.5 Quota guard

agy không báo kích thước pool hay chi phí → không dùng trần theo %. Dùng **trần tuyệt đối** từ ledger riêng theo cửa sổ trượt 5h và ngày (khởi đầu **3M token/ngày**, hiệu chỉnh ở L1 vì quota tính theo "Work Done", không theo token). 429 mở circuit breaker **lưu bền** tới mốc 5h kế tiếp. Mỗi tick bắt đầu bằng 1 batch canary (đồng thời xác nhận dòng `agent=true`).

## 4. Các phương án bị loại (có bằng chứng)

| Phương án                                                                                                                           | Lý do loại                                                                                                                                                                                                                                                    |
| -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bản nháp trước: stdin`--input-format text`, `--dangerously-skip-permissions`, schema mảng + `prefixItems`, batch 25, US-024 | F1 (stdin bị bỏ qua), ADR 0008 §2.2, F8 (schema bị từ chối), US-024 đã dùng                                                                                                                                                                            |
| Full autonomous conductor (agy tự quyết chạy script)                                                                                | Trái Rule 01 §1 / Rule 07, bug#1044/#902/#1077, rủi ro prompt injection từ bài báo với 57 tool + allowlist `.py`                                                                                                                                       |
| MCP pull-worker (claim/submit)                                                                                                         | Chạy được không cần skip-permissions [V] nhưng 7 lượt/96,5k token cho 3 bài (~2,5–30× one-shot), cache không bắc cầu, cần ngoại lệ Rule 01 §1.**D2 tự rút**; chỉ mở lại nếu telemetry L0 cho thấy mất batch do #902/#1077 > 5% |
| Worker`stream-json` sống lâu nhiều lượt                                                                                         | Context phình, rò chéo giữa batch, cache chỉ có trong cùng hội thoại nhưng không bù được chi phí                                                                                                                                                |
| Sidecar /`agentapi` / remote-control                                                                                                 | F10                                                                                                                                                                                                                                                             |
| watchdog trên thư mục OneDrive                                                                                                      | Sự kiện trùng, placeholder, file dở dang                                                                                                                                                                                                                    |
| Hook trong`morninger`                                                                                                                | Job nuốt exception, đã bận ~56%                                                                                                                                                                                                                             |
| Prefect / Dagster                                                                                                                      | Quá nặng cho một máy                                                                                                                                                                                                                                        |

## 5. Lộ trình governance (WIP = 1)

| Bước | Mã                          | Nội dung                                                                                                                                                                                                                                                                                                                                                                                                                                            | Cổng                                       |
| ------ | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| 1      | Intake**#25**          | Tier 3; đăng ký thêm ADR 0008/0009 vào bảng`decision` harness.db (hiện chỉ có 0001/0002/0006)                                                                                                                                                                                                                                                                                                                                             | —                                          |
| 2      | **ADR 0010** (nháp)   | Runner agy một-lượt không-tool;**sửa Q1** (headless chỉ cho runner này), **sửa ADR 0009 §2.3** (allow-list model), **tái kích hoạt ADR 0008 §2.2/§2.6** + standing order/thang/kill switch; provider mới; **xác nhận ToS & việc gửi nội dung tin sang Google** (tài khoản cá nhân vs miền FPTS)                                                                                                     | **H1: Human duyệt**                  |
| 3      | **US-025** (normal)    | Tiền đề:`--finish` fail-loud (bỏ `check=False`), `.pipeline.lock` Python dùng chung, assert DB path, tắt `news_cron`, sửa `settings.yaml`                                                                                                                                                                                                                                                                                           | —                                          |
| 4      | Spike A/B (scratch)          | A: 3 lệnh — hồ sơ + agent + hook, đo overhead. B: 2 lệnh — batch 50 và 100 thật, đo cắt cụt/độ trễ                                                                                                                                                                                                                                                                                                                                    | Không cần duyệt (scratch, bản sao)      |
| 5      | **US-026** (high-risk) | `agy_runner.py` + `--runner agy` ở **L0**; tham số hoá provenance (`article_expand.py:53-54`), `token_ledger --source agy`, bảng `agy_calls` (đĩa local), fixture fake-agy cho mọi lớp lỗi, thêm vào `AUTOMATION_CLIS`. **A/B ~200 bài vs DSH**: parse_fail < 2%, DoD ≥ 99% sau repair, mã nhóm sai < 5% trước repair, tỷ lệ BOTH không kém DSH quá 5 điểm, token ±20% dự báo, review mù 20 bài | Rule 07 §4 checklist →`status: active`  |
| 6      | **US-027** (high-risk) | `article_tick.py` + Task Scheduler + standing order + quota guard ở **L1**                                                                                                                                                                                                                                                                                                                                                                  | **H2: operator viết standing order** |
| 7      | —                           | L1 → L2 sau 5 wave sạch                                                                                                                                                                                                                                                                                                                                                                                                                            | **H3**                                |

Tách riêng, **không** gộp vào runner: thêm trường `m` (materiality) — đúng là thiếu [V] và `_sort_key` (`user_output.py:287-297`) chỉ đọc `materiality.score` lồng nên fallback top-level là mã chết, nhưng đây là thay đổi hợp đồng (hash prefix, expander, xlsx) → intake riêng.

## 6. Top rủi ro còn lại

1. **Prompt injection từ bài báo** — giảm bằng hồ sơ cô lập, allowlist rỗng, `tools: []`, hook deny-all, VIOLATION = FATAL-sau-2; rủi ro dư: nội dung bị lái → chỉ validator/DoD bắt.
2. **Cạn quota chung** làm nghẽn công việc tương tác → trần tuyệt đối + breaker.
3. **agy tự cập nhật phá cờ/hành vi** (1.2.7→1.2.9 trong 2 ngày); cơ chế chuyển hướng hồ sơ **chưa được tài liệu hoá** → ghim, canary, runbook.
4. **Dữ liệu ra ngoài / ToS** → quyết trong ADR 0010 trước khi chạy dữ liệu thật quy mô.
5. **Thành công giả** → bộ phân loại 3.1.
6. **Split-brain DB / xung đột OneDrive** → US-025.
7. **Hai runner ghi cùng wave** → khoá chung + runner đóng dấu trong manifest.
8. **Không chạy được khi logoff** (auth keyring) → tác vụ "Interactive only", chấp nhận.
9. **Chất lượng Gemini Flash-low chưa được chứng minh ở quy mô** (mới 15+10 bài) → A/B bắt buộc.
10. **Model bị đổi ngầm** → assert model trong `init`, ghi `model` vào meta.
