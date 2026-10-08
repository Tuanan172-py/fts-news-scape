# Vận hành tự chủ 24/7 cho Article Lane: control plane, đội agent và human-in-the-loop

- **Ngày:** 2026-10-01
- **Trạng thái:** người dùng duyệt 2026-10-01; đã triển khai P0–P5 trong kho mã (US-029, ADR 0012). D1–D7 lấy giá trị đề xuất ở §11. Phần thủ công còn lại (token Telegram, URL healthchecks, cấp standing order) ở runbook `project/docs/operations/ops-daemon.md` §1.
- **Lệch so với thiết kế khi triển khai:**
  - Phạm vi bài chờ của sensor giới hạn ở hôm nay và hôm qua. Định nghĩa của `article_tick` không lọc ngày (5.908 bài tồn tích), dùng nó thì daemon sẽ nối hàng chục đợt cho tồn đọng cũ.
  - Phím tắt dùng Ctrl+Alt+O (lối tắt Start Menu) mở quake window; `Win+`` ẩn/hiện.
  - Bảng điều khiển là TUI ANSI không phụ thuộc thư viện ngoài, thay cho Textual.
  - Telegram gọi Bot API trực tiếp qua `requests`.
- **Lane của tài liệu:** normal (nghiên cứu, thiết kế). **Lane của phần triển khai:** high-risk (automation substrate, DB vận hành mới, kênh điều khiển từ xa), cần ADR 0012 và duyệt trước khi code.
- **Kế thừa:** ADR 0010 (Article Lane duy nhất, token là số ghi nhận), ADR 0011 (runner `agy`, `article_tick.py`, `AGY_STOP`, `.pipeline.lock`), `docs/proposals/20260923-agy-automation-council.md` (thang L0→L2, standing order).

---

## 0. Tóm tắt

Pipeline đã chạy đủ các khâu end-to-end, nhưng chưa có thành phần nào **luôn sống**, **tự nhận việc** và **tự báo khi chết**. Thiết kế đề xuất gồm ba tầng:

1. **Control plane tất định** (`ops_daemon`, Python, 0 token, chạy 24/7). Một tiến trình giữ toàn bộ đồng hồ, trạng thái, timeout và quyền khởi chạy. Lớp bền dùng **DBOS** (thư viện Python, checkpoint vào SQLite riêng `C:\data\news-scape\ops.db`). Mỗi đợt là một workflow có khoá idempotent. Mỗi khâu hiện có (`article_run.py` chuẩn bị, phân tích, `--finish`, giao hàng) là một step chạy subprocess, giữ nguyên mã cũ.
2. **Worker nhận thức.** `article-processor` qua `agy` (mặc định), OpenRouter hoặc DSH (dự phòng). Thêm một vai mới là **`ops-sentinel`**: agy chạy một lượt, chỉ đọc. Vai này chẩn đoán sự cố và soạn bản tin, chỉ đề xuất chứ không tự thi hành.
3. **Mặt điều khiển của người vận hành**, chia ba lớp theo độ khẩn:
   - **Telegram bot.** Đẩy cảnh báo, nhận lệnh, có nút duyệt.
   - **Phím tắt `Win+``.** Mở một bảng điều khiển TUI thả xuống, tail nhật ký sự kiện trực tiếp.
   - **Dead-man ngoài máy** (healthchecks.io). Báo khi cả máy hoặc cả daemon chết, việc mà tiến trình cục bộ không tự báo được.

Kích hoạt: **đủ 100 bài chờ thì mở đợt**. Hai luật vét ngăn bài lẻ bị bỏ quên: bài chờ lâu nhất quá 90 phút, hoặc chạm khung giờ chốt phiên. Mỗi lúc chỉ chạy một đợt; backlog lớn được xử lý tuần tự thành nhiều đợt 100 bài.

---

## 1. Hiện trạng đo được (2026-10-01)

| Thành phần | Có gì | Thiếu gì |
|---|---|---|
| Capture (`src/morninger.py`) | APScheduler: capture/15', derive/30', reclaim/30', drift hằng ngày; khoá tệp `capture.lock` | **Khởi động tay** (đang chạy từ 28/09, không task nào giữ). Reboot hoặc logoff là mất. Không ai biết khi nó chết. |
| Trigger (`scripts/article_tick.py`) | Ngưỡng 50 bài, khung giờ vét, `.pipeline.lock`, `AGY_STOP`, standing order L0–L2 | **Chưa lên lịch** (Task Scheduler chỉ có `news_cron`, đang Disabled). Không timeout tổng cho subprocess. Không ghi trạng thái. Không báo ai khi thất bại. |
| Runner `agy` | Timeout mỗi lượt 600 s, thử lại 1 lần, phân loại `QUOTA/TIMEOUT/RETRYABLE/FATAL` | Không có circuit breaker bền giữa các đợt. Không phân biệt "mất đăng nhập" với lỗi khác. Không phát nhịp tim tiến độ. |
| Runner OpenRouter | Timeout 300 s, retry 429/5xx | Như trên. Việc chuyển provider chưa có chính sách. |
| `--finish` | Cổng kỹ thuật: DB ghi được, nạp không lỗi, độ phủ ≥ 90% | Kết quả chỉ in ra stdout. |
| Radar | `pipeline_radar.py status` cho đúng một lệnh kế tiếp | Chỉ kéo (pull), không đẩy (push). |
| Thông báo | `src/notifier/file_notify.py` ghi log tin theo luật | Là thông báo **tin tức**, không phải thông báo **vận hành**. |
| Giao hàng | `write_user_output.py` | Chạy tay. |

Tín hiệu đỏ đang có mà không ai được báo: 164 bài chờ, 1.408 Bronze dead-letter, 228 Bronze chặn watermark (radar 2026-10-01).

---

## 2. Yêu cầu thiết kế

| Mã | Yêu cầu | Đo bằng |
|---|---|---|
| R1 | Tự nhận việc: đủ 100 bài thì mở đợt, không cần người | Độ trễ từ lúc đạt ngưỡng tới lúc mở đợt ≤ 5 phút |
| R2 | Không bỏ quên bài lẻ | Tuổi bài chờ p95 ≤ 2 giờ trong giờ thị trường |
| R3 | Sống 24/7, tự hồi phục sau crash hoặc reboot | Daemon tự khởi động lại ≤ 2 phút. Đợt dang dở chạy tiếp từ step cuối đã xong. |
| R4 | Heartbeat, phát hiện chết | Daemon, capture hoặc cả máy chết thì người nhận cảnh báo ≤ 10 phút |
| R5 | Timeout với provider, báo mất kết nối | Treo không vượt deadline của step. Lỗi kết nối lặp lại thì mở breaker và cảnh báo ngay. |
| R6 | Người nắm được mọi hoạt động | Mọi hành động của mọi agent thành một dòng sự kiện, xem được qua Telegram, phím tắt và radar |
| R7 | Người can thiệp được | Tạm dừng, tiếp tục, chạy ngay, chạy lại, duyệt, đổi provider, gia hạn standing order, đều từ điện thoại |
| R8 | Không phá bất biến | Token chỉ ghi nhận. Một đợt một chương trình. `--batch` là cách chia lô duy nhất. Code-first không tính là phân tích. Không script giả lập agent. |

---

## 3. Nghiên cứu và lựa chọn framework

### 3.1 Bảng so sánh (bối cảnh: một máy Windows 11, Python, SQLite, agent CLI dưới tài khoản người dùng)

| Ứng viên | Hợp một máy Windows | Gánh vận hành | Độ bền | HITL sẵn có | Kết luận |
|---|---|---|---|---|---|
| **DBOS (Python)** | Rất tốt: thư viện, SQLite, không server | Rất nhẹ | Workflow checkpoint exactly-once | `DBOS.recv/send` chờ bền nhiều giờ | **Chọn** |
| Prefect 3 | Tốt: server SQLite | Trung bình (server, worker, UI) | Tốt | `pause_flow_run(wait_for_input)` | Phương án 2 nếu cần UI sẵn |
| Temporal | Được, nhưng bản một tiến trình chỉ là dev server | Nặng | Rất tốt | Signal/update | Quá cỡ |
| Restate | Tốt: một binary | Trung bình | Rất tốt | Awakeable | Thêm một runtime phải nuôi |
| Dagster (sensor) | Cần daemon | Nặng | Tốt cho asset | Yếu | Hướng asset, không hướng vòng agent |
| Inngest / Hatchet / Windmill / n8n | Docker, Node hoặc Postgres; worker Windows của Windmill là bản trả phí | Nặng | Tốt | Có | Loại |
| APScheduler 3.x + bảng lease tự viết | Rất tốt (đã dùng) | Rất nhẹ | Chỉ lịch bền, tiến độ trong đợt thì không | Không | **Phương án dự phòng.** Thực chất là tự viết lại một nửa DBOS |
| Task Scheduler / Servy / NSSM | Gốc Windows | Nhẹ | Chỉ khởi động lại | Không | Chỉ dùng làm **gốc cây giám sát** |
| LangGraph, OpenAI Agents SDK, MS Agent Framework, CrewAI, ADK, Pydantic AI | Thư viện | Nhẹ | Checkpointer | Có (interrupt, approval) | **Không cần.** HITL của chúng nằm trong vòng gọi tool của agent. Agent ở đây là hàm một lượt không tool (ADR 0011), nên điểm duyệt nằm ở **cấp đợt** và thuộc về lớp workflow. |

### 3.2 Lý do chọn DBOS

- **Khớp kiến trúc sẵn có.** Python là conductor, agent là worker. DBOS chỉ thêm checkpoint quanh các lệnh đang có, không bắt viết lại.
- **Khoá đợt idempotent.** Workflow ID `wave-<YYYYMMDD>-<seq>` nằm sẵn trong mô hình. Khởi chạy trùng ID không làm gì.
- **Hồi phục sau crash.** Tiến trình chết giữa đợt thì lần khởi động sau chạy tiếp từ step cuối đã xong, không đóng gói lại và không tiêu token lại cho lô đã có đầu ra.
- **Chờ người duyệt bền.** `DBOS.recv("approve", timeout)` kết hợp nút Telegram gọi `DBOS.send` là đúng mẫu duyệt cấp đợt cần dùng.
- **Không server.** Ít thành phần hơn Prefect: một tiến trình thay vì server cộng worker.
- **Rủi ro cần chứng minh trước (spike P0):**
  - DBOS khuyến nghị Postgres cho production. Với một writer và khoảng 10 đợt/ngày, SQLite đủ, nhưng phải đo trên máy này.
  - DB đặt ở `C:\data\news-scape\ops.db`, ngoài OneDrive, tách khỏi `monocle.db` để không tranh khoá ghi.
  - Spike không đạt thì rơi về phương án dự phòng: APScheduler cộng bảng `ops_waves` có `lease_until`/`heartbeat_at`.

### 3.3 Mặt giám sát cho người: các phương án đã cân nhắc

| Kênh | Đẩy/kéo | Hai chiều | Ngoài máy | Đánh giá |
|---|---|---|---|---|
| **Telegram bot** (python-telegram-bot, long polling) | Đẩy | Có (lệnh, inline keyboard) | Có, qua điện thoại | **Chọn làm kênh chính.** Long polling không cần IP public hay webhook sau NAT. |
| **healthchecks.io** (hoặc Uptime Kuma tự host) | Đẩy khi *im lặng* | Không | Có | **Chọn làm dead-man.** Cách duy nhất phát hiện được máy ngủ, mất điện hoặc daemon chết. |
| **Quake terminal `Win+``** (Windows Terminal `wt -w _quake` + TUI Textual) | Kéo | Có (phím lệnh) | Không | **Chọn làm bảng điều khiển tại bàn.** Đáp đúng ý "bấm hotkey là thấy toàn bộ log". |
| ntfy.sh | Đẩy | Hạn chế (action button gọi HTTP, cần endpoint) | Có | Dự phòng nếu Telegram bị chặn ở mạng công ty |
| Microsoft Teams webhook | Đẩy | Không | Có | Hợp khi cần chia sẻ trong FPTS. Webhook chỉ một chiều. |
| Windows toast | Đẩy | Không | Không | Chỉ hữu ích khi ngồi ở máy. Có thể bổ sung, không thay được. |
| Datasette trên `ops.db` | Kéo | Không | Không | Tra cứu sâu, lọc sự kiện theo đợt. Tuỳ chọn. |
| Arize Phoenix / Langfuse | Kéo | Không | Không | **Hoãn.** Worker là CLI một lượt. Token và chi phí đã có `token_ledger`. Langfuse cần ClickHouse, Redis và S3, quá nặng cho một máy. |

---

## 4. Kiến trúc đích

```
                    ┌───────────────────────── HUMAN (người vận hành) ─────────────────────────┐
                    │  📱 Telegram: cảnh báo · bản tin · nút duyệt · lệnh /pause /run /retry      │
                    │  ⌨  Win+`  : ops_console (TUI) — sự kiện trực tiếp + radar + đợt đang chạy │
                    │  ✉  healthchecks.io: báo khi hệ thống IM LẶNG (máy ngủ/daemon chết)         │
                    └──────────────▲───────────────────────────▲─────────────────────▲──────────┘
                                   │ outbox (gửi lại được)     │ đọc ops_events      │ ping 60s
┌──────────────────────────────────┴───────────────────────────┴─────────────────────┴──────────┐
│ ops_daemon  (Python, 0 token, 1 tiến trình, Task Scheduler "At log on" + restart-on-failure)  │
│                                                                                                │
│  ┌ Supervisor ─────────────┐  ┌ Wave sensor (mỗi 2') ─┐  ┌ Health probes (mỗi 60') ─────────┐ │
│  │ giữ con: morninger      │  │ pending ≥100 | tuổi   │  │ capture tươi? DB ghi được? đĩa?  │ │
│  │ restart có trần K/T     │  │ >90' | khung giờ vét   │  │ breaker? standing order hạn?     │ │
│  └─────────┬───────────────┘  └──────────┬────────────┘  │ dead-letter tăng? agy version?   │ │
│            │                             ▼               └──────────────────────────────────┘ │
│            │            ┌ Wave workflow (DBOS, id = wave-YYYYMMDD-NN) ───────────────────────┐ │
│            │            │ preflight → prepare → [canary] → analyze → repair? → [gate L1]     │ │
│            │            │          → finish → [gate L2] → deliver? → digest                  │ │
│            │            │ mỗi step = subprocess lệnh sẵn có · deadline riêng · kill cả cây   │ │
│            │            └──────────────┬─────────────────────────────────────────────────────┘ │
│            │                           │ phát sự kiện                                           │
│  ┌─────────▼───────────────────────────▼─────────┐   ┌ Telegram bot (long polling, thread) ┐  │
│  │ ops.db: ops_events · ops_alerts(outbox) ·     │◄──┤ chat_id whitelist · lệnh → DBOS.send │  │
│  │ provider_breakers · DBOS system tables        │   └──────────────────────────────────────┘  │
│  └───────────────────────────────────────────────┘                                           │
└───────────────┬──────────────────────────────────────────────┬────────────────────────────────┘
                │ subprocess (deadline, Job Object)            │ chỉ khi sự cố / cuối ngày
        ┌───────▼────────┐  ┌──────────────┐  ┌───────────┐   ┌▼──────────────────────────────┐
        │ article_run.py │→ │ agy runner   │  │ openrouter│   │ ops-sentinel (agy, 1 lượt,    │
        │ pack/finish    │  │ (mặc định)   │  │ (dự phòng)│   │ chỉ đọc): chẩn đoán + đề xuất │
        └───────┬────────┘  └──────────────┘  └───────────┘   └───────────────────────────────┘
                ▼
     C:\data\news-scape\monocle.db  (không đổi lược đồ)
```

### 4.1 Nguyên tắc phân vai

| Vai | Ai | Được làm | Không được làm |
|---|---|---|---|
| **Control plane** | `ops_daemon` (Python) | Lịch, trạng thái, timeout, kill, retry, breaker, khởi chạy step, gửi cảnh báo | Sinh nội dung ngữ nghĩa |
| **Worker phân tích** | `article-processor` qua agy/OpenRouter/DSH | Phân tích trọn bài, một lượt, không tool | Gọi lệnh, đọc tệp, quyết định luồng |
| **Trực ban sự cố** | `ops-sentinel` (agy, một lượt, chỉ đọc) | Đọc trích đoạn `ops_events` và log, chẩn đoán, đề xuất **một** lệnh trong danh sách trắng | Thi hành bất cứ gì. Lệnh chỉ chạy sau khi người bấm nút. |
| **Người vận hành** | Bạn | Viết và gia hạn standing order, duyệt tại các cổng, xử lý cảnh báo đỏ | Phải có mặt để pipeline chạy |

**Về ý định "agent nền điều phối là agy".** Đề xuất giữ agy ở vai **trực ban nhận thức** (`ops-sentinel`), **không** đặt agy làm vòng lặp điều phối 24/7. Lý do:

1. Sự kiện cần báo nhiều nhất là provider mất kết nối hoặc hết quota. Nếu điều phối viên chạy trên chính provider đó, nó chết cùng lúc với sự cố và không còn ai để báo.
2. Nhịp tim, timeout và kill phải tất định và không tốn quota. Một vòng LLM chạy mỗi 2 phút sẽ tiêu pool "Work Done" 5 giờ của Antigravity cho việc mà ba dòng SQL làm được.
3. ADR 0011 đã chốt "Python là conductor, agy là hàm nhận thức thuần". Thiết kế này mở rộng ADR đó, không đảo ngược nó.

Agy vẫn là bộ não ở những chỗ cần phán đoán: chẩn đoán lỗi lạ, viết bản tin cuối ngày, đề xuất cách gỡ. Khi agy mất kết nối, control plane vẫn báo được.

### 4.2 Gốc cây giám sát trên Windows

| Tầng | Ai giám sát | Chính sách |
|---|---|---|
| Máy và daemon | healthchecks.io (ngoài máy) | Daemon ping mỗi 60 s, chu kỳ 5', grace 5'. Im lặng thì gửi email và Telegram từ phía healthchecks. |
| Daemon | Task Scheduler: "At log on", **Run only when user is logged on**, restart on failure mỗi 1' | Không dùng Windows service hay "run whether logged on or not", vì agy dùng thông tin đăng nhập trong hồ sơ người dùng và Session 0 không thấy được. |
| `morninger` | Supervisor trong daemon | Restart với backoff 10 s→5'. Quá 5 lần trong 30' thì dừng restart và gửi cảnh báo đỏ. |
| Step của đợt | DBOS + deadline | Hết deadline thì kill cả cây tiến trình (psutil, Job Object), đánh dấu `TIMEOUT` và áp chính sách retry của step. |
| Lượt gọi provider | Runner (đã có) | Timeout 600 s (agy), 300 s (OpenRouter), retry 1 lần |

Chuẩn bị máy (một lần):
- `powercfg`: tắt sleep và hibernate khi cắm điện.
- Daemon giữ `wakepy`/`PowerSetRequest` trong lúc chạy đợt.
- Hẹn giờ Windows Update.
- Loại trừ `C:\data\news-scape` khỏi Defender real-time scan.
- Cân nhắc auto-logon nếu đây là máy chuyên dụng.

---

## 5. Quy trình đợt (wave workflow)

### 5.1 Luật kích hoạt (wave sensor, mỗi 2 phút, 0 token)

Sensor bỏ qua chu kỳ khi có `AGY_STOP`, khi `ops_paused` bật, khi một đợt đang chạy (WIP đợt = 1), hoặc khi breaker của provider chính đang OPEN mà chưa có quyền chuyển provider. Ngoài các trường hợp đó, sensor mở đợt khi thoả **một** trong ba điều kiện:

| Luật | Điều kiện | Lý do |
|---|---|---|
| T1 Khối lượng | `pending ≥ 100` | Yêu cầu chính |
| T2 Tuổi | `pending > 0` và bài chờ lâu nhất > 90 phút | Ban đêm hoặc cuối tuần có thể không bao giờ đủ 100 |
| T3 Khung giờ | `pending > 0` trong 07:15/12:15/15:15/17:15 ±15' | Giữ hành vi của `article_tick.py` |

- Mỗi đợt lấy `limit = 100` bài, chia `--batch 50` cho agy (theo ADR 0011).
- Backlog lớn, ví dụ 528 bài, được chạy thành chuỗi đợt nối tiếp. Đợt sau chỉ mở khi đợt trước kết thúc.
- `pending` lấy đúng định nghĩa của radar và `count_pending_articles`: có gói Silver, chưa có `l1_outputs` đạt và không phải code-first.

### 5.2 Máy trạng thái của một đợt

```
SENSED → PREFLIGHT → PREPARED → CANARY → ANALYZING → (REPAIRING ≤2) → ANALYZED
   → [L1: AWAIT_APPROVAL] → FINISHING → DONE → [L3: DELIVERING → DELIVERED]
Mọi trạng thái → FAILED(lý_do) | PARKED(chờ người) | CANCELLED(người huỷ)
```

| Step | Lệnh sẵn có | Deadline | Retry | Khi thất bại |
|---|---|---|---|---|
| preflight | `article_run.py --where` + kiểm DB ghi được, đĩa trống ≥ 5 GB, prefix khớp | 1' | 0 | PARKED, cảnh báo đỏ |
| prepare | `article_run.py --wave W --runner agy --limit 100 --batch 50` | 5' | 1 | FAILED |
| canary | phân tích 1 lô 5 bài trước (tuỳ chọn, bật khi breaker vừa HALF_OPEN) | 12' | 0 | Breaker về OPEN, PARKED |
| analyze | `article_run.py --wave W --runner agy --analyze` | 45' tổng; tiến độ im lặng 15' thì coi là treo | Theo phân loại lỗi (§6) | REPAIRING hoặc PARKED |
| repair | `article_run.py --wave W --repair` (chỉ lô thiếu bài) | 20' | tối đa 2 vòng | PARKED, cảnh báo |
| finish | `article_run.py --wave W --runner agy --finish` (cổng kỹ thuật ≥ 90%) | 10' | 0 (cổng đã fail-loud) | FAILED + cảnh báo đỏ, không tự lặp |
| deliver (L3) | `write_user_output.py --date today` | 5' | 2 (tệp bị Excel khoá) | Cảnh báo vàng |

**Nhịp tim tiến độ.** Step `analyze` không có mốc trung gian nếu chỉ nhìn mã thoát. Daemon đo tiến độ bằng số tệp `*.output.json` mới của đợt trong `data/agent_outputs_article/` (0 token, không sửa runner). Hướng tốt hơn ở P3: runner ghi một dòng `progress` mỗi khi xong một lô vào `ops_events`.

### 5.3 Thang tự chủ (mở rộng thang của hội đồng 23/09)

| Mức | Tự làm | Dừng chờ người | Điều kiện lên mức |
|---|---|---|---|
| L0 | Chỉ cảnh báo "đủ ngưỡng, gõ lệnh" | Mọi thứ | Mặc định khi mới cài |
| L1 | preflight → analyze | Trước `--finish`: Telegram gửi tóm tắt và nút **[Nạp DB] [Xem lỗi] [Huỷ]**. Không ai bấm trong 2 giờ thì đợt PARKED. | Standing order còn hạn |
| L2 | Thêm `--finish` | Chỉ khi cổng đỏ hoặc có sự cố | 5 đợt L1 sạch liên tiếp |
| L3 | Thêm giao xlsx | Chỉ khi có sự cố | 5 ngày L2 sạch, người bật |

- **Tự hạ mức.** 2 đợt hỏng liên tiếp thì hạ một bậc và cảnh báo đỏ.
- **Standing order.** Do người tạo, thời hạn ≤ 7 ngày. Gia hạn được bằng `/order extend 7`. Hash của standing order ghi vào mỗi đợt.
- **Bỏ "quota guard trần 3M token/ngày"** của bản hội đồng 23/09, vì trái ADR 0010 ("token là số ghi nhận, không phải cổng"). Quota chỉ được xử lý **phản ứng**: provider báo 429 thì mở breaker.

---

## 6. Provider: timeout, circuit breaker, mất kết nối

### 6.1 Phân loại lỗi

Kế thừa trạng thái mà runner đã trả về, bổ sung lớp `AUTH` và `NETWORK`.

| Lớp | Nhận diện | Hành động |
|---|---|---|
| OK | Có đầu ra, parse đạt | Đóng breaker nếu đang HALF_OPEN |
| TIMEOUT | Quá `--print-timeout` hoặc deadline tiến trình | Đếm. 3 lần liên tiếp thì OPEN 30'. |
| NETWORK | DNS, connection reset, không tới host | Đếm. 3 lần liên tiếp thì OPEN 10' kèm backoff, **cảnh báo "mất kết nối provider"**. |
| QUOTA | 429 / `resource_exhausted` | OPEN tới mốc làm mới 5 giờ của pool, cảnh báo vàng kèm giờ mở lại |
| AUTH | 401/403, "login required", token hết hạn | OPEN vô thời hạn, **cảnh báo đỏ "cần đăng nhập lại agy"** kèm lệnh cụ thể |
| EMPTY | Mã thoát 0 nhưng stdout rỗng (lỗi agy đã biết khi stdout là pipe) | Coi như RETRYABLE. Lặp 2 lần thì đối xử như TIMEOUT. |
| FATAL / VIOLATION | Lỗi packet, gọi tool | Không retry, PARKED, cảnh báo |

### 6.2 Breaker bền

Bảng `provider_breakers(provider, state, opened_at, reopen_at, reason, consecutive_failures)` nằm trong `ops.db`, nên vẫn còn sau khi daemon khởi động lại. Khi tới `reopen_at`, breaker chuyển sang HALF_OPEN và chạy một lô canary.

### 6.3 Chuyển provider

Lệnh `/provider` trên Telegram đặt chính sách `failover` trong standing order:

| Giá trị | Hành vi |
|---|---|
| `never` | Mặc định. Chờ breaker mở lại. |
| `ask` | Gửi nút **[Chuyển OpenRouter] [Chờ]**. |
| `auto` | Tự chuyển, nhưng chỉ khi người đã duyệt trước điều kiện dữ liệu và chi phí của OpenRouter. |

Đầu ra của mọi provider đi qua cùng hai cổng DoD, provenance ghi theo provider.

### 6.4 Phát hiện "agent mất kết nối"

Ba tín hiệu độc lập, không phụ thuộc lẫn nhau:

1. **Breaker OPEN** với lớp NETWORK hoặc AUTH. Cảnh báo ngay.
2. **Tiến độ đợt đứng yên** quá 15'. Daemon kill cây tiến trình và cảnh báo.
3. **Daemon im lặng**. healthchecks.io báo, kể cả khi máy mất mạng hoặc tắt nguồn.

---

## 7. Quan sát: một dòng sự kiện cho mọi thứ

### 7.1 `ops_events`: nguồn sự thật duy nhất của vận hành

Lược đồ trong `ops.db`, chỉ ghi thêm:

```
ops_events(id, ts, level{debug,info,warn,error,critical}, actor{daemon,sensor,wave,runner,
           sentinel,human,bot}, wave_id, step, kind, message, data_json)
```

- `kind` ví dụ: `wave.opened`, `step.started`, `step.done`, `batch.done`, `breaker.opened`, `heartbeat.missed`, `human.command`, `approval.requested`, `approval.granted`.
- Mọi kênh (Telegram, TUI, radar) **chỉ đọc** bảng này. Không kênh nào có trạng thái riêng.
- Đồng thời ghi JSONL theo ngày tại `C:\data\news-scape\ops_logs\YYYY-MM-DD.jsonl` để grep và lưu trữ.
- stdout và stderr của mọi subprocess được ghi vào `ops_logs\waves\<wave>\<step>.log`. Sự kiện chỉ giữ 20 dòng cuối khi lỗi.
- Lệnh do người gõ qua bot cũng thành sự kiện (`actor=human`), làm vết kiểm toán.

### 7.2 Outbox cảnh báo

- `ops_alerts(id, created_at, severity, dedup_key, text, buttons_json, sent_at, attempts)`.
- Một luồng riêng gửi Telegram và thử lại nếu Telegram lỗi. Cảnh báo không mất khi mạng chập chờn.
- `dedup_key` gộp các cảnh báo lặp: cùng khoá trong 30' chỉ gửi một tin, kèm đếm số lần.

### 7.3 Ma trận mức độ

| Mức | Ví dụ | Kênh | Cần người? |
|---|---|---|---|
| 🔴 critical | Daemon/máy chết (healthchecks), AUTH, `--finish` đỏ, capture chết > 30' trong giờ thị trường, morninger vượt trần restart | Telegram có âm thanh + healthchecks email | Có, ngay |
| 🟠 error | Breaker OPEN, đợt PARKED, 2 đợt hỏng liên tiếp (tự hạ mức), dead-letter tăng > 50/ngày | Telegram | Có, trong ngày |
| 🟡 warn | QUOTA (có giờ mở lại), repair vòng 2, standing order còn < 24h | Telegram im lặng | Không bắt buộc |
| 🟢 info | Đợt xong (số bài, độ phủ, token, thời gian) | Gom vào bản tin, hoặc tin im lặng | Không |
| 📰 digest | 08:00 và 18:00: số bài, số đợt, độ phủ, backlog, token/USD, sự cố, việc cần người | Telegram | Không |

---

## 8. Mặt điều khiển của người

### 8.1 Telegram bot

Tập lệnh tối thiểu, mỗi lệnh ánh xạ tới một lệnh 0 token có sẵn hoặc một `DBOS.send`:

| Lệnh | Tác dụng |
|---|---|
| `/status` | Bản rút gọn của `pipeline_radar.py status`, cộng đợt đang chạy, breaker, mức tự chủ |
| `/waves [n]` | n đợt gần nhất: trạng thái, số bài, độ phủ, thời lượng |
| `/log [n] [wave]` | n sự kiện cuối |
| `/pause` · `/resume` | Bật/tắt `ops_paused` (sensor ngừng mở đợt mới, đợt đang chạy chạy tiếp) |
| `/stop` | Tạo `AGY_STOP` và huỷ đợt đang chạy ở ranh giới step kế tiếp (xác nhận hai bước) |
| `/run` | Mở đợt ngay, bỏ qua ngưỡng (tương đương `article_tick --force`) |
| `/retry <wave>` | Chạy lại đợt PARKED/FAILED từ step hỏng |
| `/approve <wave>` · `/reject <wave>` | Cổng L1 (cũng có trên nút bấm) |
| `/level L0..L3` · `/order extend <ngày>` | Đổi mức tự chủ, gia hạn standing order (ghi sự kiện và trace harness) |
| `/provider agy\|openrouter` · `/failover never\|ask\|auto` | Chính sách provider |
| `/diagnose [wave]` | Gọi `ops-sentinel` chẩn đoán, trả về giả thuyết và **một** lệnh đề xuất có nút **[Chạy]** |

An toàn:
- Chỉ nhận lệnh từ `chat_id` trong danh sách trắng.
- Token bot lưu trong Windows Credential Manager hoặc biến môi trường người dùng, không lưu trong kho mã.
- Lệnh phá huỷ cần xác nhận hai bước.
- Bot chỉ gửi **siêu dữ liệu vận hành** (số đếm, mã đợt, lỗi), **không** gửi nội dung bài hay đầu ra phân tích.

### 8.2 Phím tắt `Win+``: ops console

- Windows Terminal ở quake mode (`wt -w _quake`), profile mặc định chạy `python scripts/ops_console.py`.
- TUI Textual gồm bốn khung:
  1. Thanh trạng thái: daemon, capture, breaker, mức tự chủ, backlog, tuổi bài chờ lâu nhất.
  2. Đợt đang chạy: step, tiến độ lô, thời gian còn tới deadline.
  3. Dòng sự kiện trực tiếp, lọc được theo mức độ và đợt.
  4. Ô lệnh dùng chung tập lệnh với Telegram.
- Lệnh từ console cũng đi qua `DBOS.send` và cũng ghi `actor=human`.
- Phương án nhẹ hơn nếu chưa cần TUI: profile quake chạy `ops_console.py --tail`, một bản `rich` chỉ đọc.

### 8.3 Radar

Radar thêm một mục "4. VẬN HÀNH TỰ CHỦ" (daemon sống, mức tự chủ, breaker, đợt đang chạy, cảnh báo chưa xử lý). Radar vẫn là điểm vào của phiên điều phối thủ công theo Rule 08.

---

## 9. Bảng sự cố (FMEA rút gọn)

| Sự cố | Phát hiện | Tự xử lý | Người nhận gì |
|---|---|---|---|
| agy treo không trả | Deadline step / tiến độ im lặng 15' | Kill cây, retry hoặc repair | 🟠 nếu lặp |
| Mất mạng | NETWORK ×3 | Breaker OPEN, backoff | 🟠 "mất kết nối provider", tin "đã kết nối lại" khi HALF_OPEN đạt |
| Hết pool 5h | QUOTA | OPEN tới mốc làm mới | 🟡 kèm giờ chạy lại |
| agy hết phiên đăng nhập | AUTH | OPEN vô hạn | 🔴 kèm lệnh đăng nhập lại |
| Daemon crash | Task Scheduler | Restart, DBOS chạy tiếp đợt dở | 🟢 sự kiện `daemon.restarted`. Lặp > 3/giờ thì 🔴 |
| Máy ngủ / mất điện / reboot | healthchecks im lặng | Khởi động lại khi đăng nhập | 🔴 từ healthchecks |
| Capture chết | Bài mới nhất > 30' trong giờ thị trường | Supervisor restart morninger | 🟠, hoặc 🔴 nếu quá trần restart |
| DB khoá / không ghi được | preflight | Không mở đợt (không tốn token) | 🔴 |
| `--finish` độ phủ < 90% | Mã thoát ≠ 0 | Không tự lặp. Tự hạ mức nếu lặp. | 🔴 kèm `/diagnose` |
| Bronze dead-letter tăng | Probe đếm `silver_failures` | Không tự xử lý (cần sửa gốc) | 🟠 trong bản tin, kèm lệnh của radar |
| Excel đang mở tệp giao hàng | `PermissionError` | Ghi tạm rồi `os.replace`, retry | 🟡 |
| Telegram sập | Outbox gửi lỗi | Giữ trong outbox, gửi lại | Tin dồn khi kết nối lại. healthchecks vẫn báo độc lập. |
| Bot bị người lạ nhắn | `chat_id` ngoài danh sách | Bỏ qua, ghi sự kiện | 🟡 |

---

## 10. Lộ trình triển khai (WIP = 1, mỗi phase một story, có bằng chứng)

| Phase | Story | Nội dung | Lane | Bằng chứng nghiệm thu |
|---|---|---|---|---|
| P0 | ADR 0012 + spike | Duyệt thiết kế. Spike DBOS-SQLite trên máy này: workflow 3 step, kill giữa chừng, chạy lại tiếp được. | high-risk (H: duyệt) | Spike pass. Không pass thì chốt phương án dự phòng APScheduler + lease. |
| P1 | Quan sát trước, tự động sau | `ops.db` (`ops_events`, `ops_alerts`), Telegram **chỉ gửi đi**, healthchecks ping, bản tin 08:00/18:00, probe sức khoẻ. **Chưa đổi cách chạy đợt.** | high-risk | 48 giờ chạy. Tắt máy thì nhận cảnh báo ≤ 10'. Kill morninger thì nhận cảnh báo. |
| P2 | Daemon + sensor ở L1 | Daemon giữ morninger. Sensor T1/T2/T3. Workflow đợt tới ANALYZED rồi chờ nút duyệt. Thay lịch của `article_tick.py`; logic ngưỡng giữ trong module chung. | high-risk | 5 đợt L1 sạch. Kill daemon giữa analyze thì đợt chạy tiếp, không đóng gói lại. |
| P3 | Độ bền provider | Phân loại lỗi mở rộng, breaker bền, canary, deadline và kill cây, nhịp tiến độ theo lô | normal | Chaos test bằng fake-agy: treo, 429, 401, stdout rỗng, mất mạng. Mỗi ca ra đúng trạng thái và đúng cảnh báo. |
| P4 | Điều khiển hai chiều | Lệnh Telegram đầy đủ + `ops_console` TUI + phím tắt. Lên L2. | normal | Mọi lệnh bảng §8.1 có test. Lệnh nào cũng sinh sự kiện `actor=human`. |
| P5 | Trực ban nhận thức | `ops-sentinel` (registry: draft → active theo Rule 07), `/diagnose`, bản tin có diễn giải. Đánh giá L3. | normal | 10 sự cố ghi lại: sentinel đề xuất đúng lệnh ≥ 8/10, không bao giờ tự thi hành. |

Cấu trúc tệp dự kiến (mới; không sửa lược đồ `monocle.db`):

```
project/src/ops/        daemon.py · sensor.py · wave_flow.py · supervisor.py · breakers.py
                        events.py · alerts.py · telegram_bot.py · probes.py
project/scripts/        ops_daemon.py · ops_console.py · ops_install.ps1 (Task Scheduler, quake profile, powercfg)
project/config/ops.yaml ngưỡng, deadline, lịch bản tin, chính sách breaker (không chứa bí mật)
C:\data\news-scape\     ops.db · ops_logs\ · AGY_STOP · agy_standing_order.yaml
.agents/registry.yaml   master-orchestrator → hiện thực bằng ops_daemon; thêm ops-sentinel (draft)
```

---

## 11. Quyết định cần người vận hành chốt

Cột "Đề xuất" là giá trị mặc định nếu không có ý kiến khác.

| # | Câu hỏi | Đề xuất |
|---|---|---|
| D1 | Telegram có được dùng theo chính sách FPTS không (chỉ siêu dữ liệu vận hành, không nội dung)? | Có. Dự phòng: ntfy hoặc webhook Teams. |
| D2 | Máy chạy 24/7 là máy nào (laptop đang dùng hay máy chuyên dụng)? Có auto-logon được không? | Máy chuyên dụng + auto-logon. Nếu là laptop thì chấp nhận khoảng trống khi gập máy, healthchecks sẽ báo. |
| D3 | DBOS (thêm phụ thuộc mới) hay tự viết bảng lease trên APScheduler? | DBOS, có spike P0 làm cổng |
| D4 | Mức tự chủ đích sau 2 tuần | L2 (tự nạp DB). Giao xlsx (L3) bật sau. |
| D5 | Chuyển sang OpenRouter khi agy sập | `ask` (bấm nút) |
| D6 | Luật tuổi T2: 90 phút có hợp nhịp tin không? Ban đêm có cần chạy không? | 90' trong 06:00–22:00. Ban đêm chỉ T1. |
| D7 | Có cần ai khác ngoài bạn nhận cảnh báo không? | Một `chat_id` |

---

## 12. Nguồn tham khảo

- DBOS: [SQLite mặc định](https://docs.dbos.dev/ai/ai-quickstart) · [human-in-the-loop](https://docs.dbos.dev/python/examples/agent-inbox) · [queue và rate limit](https://docs.dbos.dev/python/tutorials/queue-tutorial) · [scheduled workflow](https://docs.dbos.dev/python/tutorials/scheduled-workflows)
- [Prefect interactive workflows](https://docs.prefect.io/v3/advanced/interactive) · [Temporal dev server](https://docs.temporal.io/cli/server) · [Dagster sensors](https://docs.dagster.io/guides/automate/sensors) · [Windmill Windows workers](https://www.windmill.dev/docs/misc/windows_workers)
- HITL trong framework agent: [LangGraph](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) · [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/human_in_the_loop/) · [MS Agent Framework](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop)
- Windows: [Session 0 isolation](https://kb.firedaemon.com/support/solutions/articles/4000086228-what-is-session-0-isolation-what-do-i-need-to-know-about-it-) · [Task Scheduler logon modes](https://learn.microsoft.com/en-us/answers/questions/5789906/scheduler-tasks-with-security-options-run-whether) · [Modern Standby](https://comcomponent.com/en/blog/windows-sleep-modern-standby-long-running-apps/) · [Servy vs NSSM vs WinSW](https://github.com/aelassas/servy/wiki/Comparison-with-Alternatives) · [Windows Terminal quake mode](https://maketecheasier.com/windows-terminal-quake-mode/)
- [Telegram Bot API](https://core.telegram.org/bots/api) · [PTB inline keyboard](https://docs.python-telegram-bot.org/en/v21.8/examples.inlinekeyboard.html) · [healthchecks.io API](https://healthchecks.io/docs/http_api/)
- agy: [headless](https://antigravity.google/docs/cli/headless/) · [lỗi stdout rỗng khi pipe](https://gist.github.com/allahsan/a9a9e9c8a49aecede67ce974e64ef3cf)
