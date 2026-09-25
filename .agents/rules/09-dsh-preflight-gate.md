---
trigger: always_on
---
# 09 — Cổng Nghiệm Thu Hạ Tầng Trước Khi Vận Hành (DSH Preflight Gate)

Quy chuẩn bắt buộc mọi phiên chạy trên DSH phải qua cổng nghiệm thu hạ tầng **trước** khi gõ lệnh đợt. Cổng này 0 token và chạy bằng `pwsh` + `read`.

---

## 1. Vì Sao Có Cổng Này

Preset DSH nạp **lúc mount**, không phải lúc sửa tệp. Sửa tệp xong mà không nạp lại là **trạng thái hỏng im lặng**: YAML vẫn đúng, prefix vẫn đúng, junction vẫn đúng, nhưng runtime chạy bản cũ. Triệu chứng duy nhất là **hoá đơn sai**, phát hiện sau khi đã tiêu tiền.

Bằng chứng: host `dsh web` khởi động 18/09 17:46; `agent.cordis.yml` sửa 21/09 13:43 — toàn bộ đợt tối ưu bộ nhớ đệm **chưa từng có hiệu lực** trong khi mọi dấu hiệu bề mặt đều xanh.

**Nguyên lý bao trùm:** biến trạng thái hỏng im lặng thành **lỗi ồn ào**, và làm việc đó bằng số đo chứ không bằng cảm nhận.

---

## 2. Bất Biến

1. **Không tin YAML, tin runtime.** Khoá YAML gõ sai bị **bỏ qua im lặng**. Mọi khẳng định về cấu hình phải kiểm bằng tập tool hiệu lực, không bằng cách đọc tệp.
2. **Thời điểm mount là chân lý.** So `StartTime` của tiến trình giữ cổng 3080 với `LastWriteTime` của preset. Tệp mới hơn tiến trình ⇒ bản sửa **chưa có hiệu lực**.
3. **Không có mục XÁM.** Mỗi hạng mục là ĐỎ hoặc XANH. "Chắc là được" tính là ĐỎ.
4. **ĐỎ chặn đợt.** Không có ngoại lệ "chạy tạm rồi sửa sau".
5. **Ranh giới quyền được đo, không được đoán.** Trước khi khai một việc là "người phải làm", phải chứng minh Conductor không làm được.

---

## 3. Bảng Phân Định: Tệp Nào Nạp Lúc Mount, Tệp Nào Đọc Live

Sửa sai loại tệp thì hoặc restart vô ích, hoặc tưởng đã xong mà thực ra chưa. Bảng này là thứ tự tra trước khi kết luận.

| Tệp | Cơ chế nạp | Sửa có cần restart host? |
|---|---|---|
| `agent.cordis.yml` | nạp lúc **mount** | **CÓ** |
| `preset.yml` | nạp lúc **mount** | **CÓ** |
| `~/.dsh/settings.yaml` | nạp lúc **mount** | **CÓ** |
| `skills/**/SKILL.md` | đọc **live** từ đĩa mỗi lần gọi | Không |
| `.agents/rules/*.md` | đọc khi phiên nạp `AGENTS.md` | Không |
| `RUNBOOK-*.md` | agent `read` khi cần | Không |
| `project/scripts/*.py` | tiến trình mới mỗi lần chạy | Không |

**Phép thử cho tệp nghi ngờ:** sửa tệp sau khi host đã chạy, rồi gọi lại nguồn đọc nó. Thấy nội dung mới ⇒ đọc live, không cần restart.

---

## 4. Mười Bốn Hạng Mục Nghiệm Thu

Chạy **toàn bộ** trong **một** lệnh `run_code`. Không tách bước — mỗi bước gửi lại toàn bộ lịch sử.

### Nhóm A — Định danh phiên (chặn cứng)

| # | Hạng mục | Cách kiểm | ĐẠT khi |
|:-:|---|---|---|
| A1 | Junction preset sống | `(Get-Item "$env:USERPROFILE\.dsh\.agent-presets\news-scape-conductor").Target` | Trỏ đúng `.agents\dsh\presets\news-scape-conductor` |
| A2 | Preset mặc định đúng | `settings.yaml` → `agent-presets.default` | `news-scape-conductor` |
| A3 | **Preset nạp lại sau lần sửa cuối** | So `StartTime` tiến trình cổng 3080 với `LastWriteTime` của `agent.cordis.yml` | **StartTime > mtime preset** |
| A4 | Phiên đúng preset | Tập tool trực tiếp chỉ có `run_code`; SDK có `pwsh`, `read`, `write`, `agent_article` | Đủ cả hai vế |

### Nhóm B — Bộ nhớ đệm tiền tố

| # | Hạng mục | Cách kiểm | ĐẠT khi |
|:-:|---|---|---|
| B1 | Prefix khớp catalog | `article_run.py --check-prefix` | exit 0 |
| B2 | Persona khớp prefix | cùng lệnh trên (kiểm cả hai vế) | exit 0 |

Persona lệch prefix là **lỗi duy nhất không có triệu chứng nào ngoài hoá đơn**. Dán thiếu một dòng thì kết quả vẫn đúng, chỉ có phần lẽ ra rẻ nhất đắt lên hàng chục lần.

### Nhóm C — Hợp đồng runtime

| # | Hạng mục | Cách kiểm | ĐẠT khi |
|:-:|---|---|---|
| C1 | `reasoningEffort` tắt | `settings.yaml` → `agent-default-model.reasoningEffort` | `off` |
| C2 | Permission đủ | `permission.defaultPreset` | `workspace-write` cho đợt thật |
| C3 | `mode: ptc` nguyên vẹn | `grep "mode: ptc"` trong preset | Có mặt — đổi sang `native` là output con rơi vào ngữ cảnh cha |
| C4 | Vite watcher | Xem §6 | Không có ⇒ **đừng trông vào HMR** (thông tin, không chặn) |

### Nhóm D — Sẵn sàng dữ liệu

| # | Hạng mục | Cách kiểm | ĐẠT khi |
|:-:|---|---|---|
| D1 | Script đường article đủ | Glob 13 script bắt buộc | Đủ 13/13 |
| D2 | Task `failed` đã xử lý | `pipeline_radar.py status` | Không còn tồn đọng |
| D3 | Ngày dữ liệu khớp `--date` | Đối chiếu radar | Cùng một ngày, có bài chờ |
| D4 | Áp suất ngữ cảnh | `ctx_probe.py` | 🟢 <25% |

---

## 5. Ranh Giới Năng Lực

### 5.1 Conductor TỰ LÀM được

Đọc/ghi trong repo · ghi vào `%USERPROFILE%\.dsh\` · đọc `settings.yaml` · chạy mọi script dự án qua `pwsh` · kiểm junction · sửa `agent.cordis.yml`, `preset.yml`, tài liệu.

**Ranh giới thật:** Conductor không bị chặn bởi *quyền ghi*. Nó bị chặn bởi **vòng đời tiến trình** — nó là khách bên trong host, không phải chủ của host.

### 5.2 Chỉ NGƯỜI VẬN HÀNH làm được

| # | Việc | Vì sao Conductor không làm được |
|:-:|---|---|
| 1 | **Restart host `dsh web`** | Conductor chạy *bên trong* tiến trình đó. Kill nó = tự sát giữa lượt |
| 2 | **Chọn preset lúc mở phiên** | Xảy ra ở tầng UI, **trước** khi Conductor tồn tại |
| 3 | **Mở phiên mới** | Mọi phiên đều có cha là host |
| 4 | **Đổi permission preset của phiên** | Là cấu hình giao diện |
| 5 | **Duyệt/từ chối prompt** | Approval có thể đang tắt ⇒ bị từ chối tự động |
| 6 | **Nâng cấp DSH** (`npx`) | Ghi đè chính checkout đang chạy |
| 7 | **Bật `dev:web` (Vite watcher)** | Cần tiến trình nền sống ngoài phiên |

**Chọn preset TRƯỚC khi gửi tin đầu tiên.** Preset nạp lúc mount; đổi sau khi phiên đã mở **không có tác dụng**. Sai preset là mất toàn bộ ranh giới công cụ của agent con — nguyên nhân gốc vệt 845 nghìn token ngày 17/09.

---

## 6. Hai Cạm Bẫy Đo Lường (Đã Trả Giá)

1. **`Get-NetTCPConnection` trả RỖNG dưới sandbox** — không phải server chết. Cmdlet này bị chặn quyền, sẽ báo `NO SERVER ON 3080` một cách sai lệch và suýt khiến kết luận là phải restart.
   - **Lấy PID bằng `netstat -ano | Select-String ":3080"`, không bằng `Get-NetTCPConnection`.**
   - `Get-CimInstance Win32_Process` cũng bị chặn (`Access denied`) — đừng dùng nó để đọc `CommandLine`.

2. **Kiểm junction mất là chuyện thường** sau khi di chuyển OneDrive, đổi máy, hoặc clone mới.
   - Sửa: `cmd /c mklink /J` theo `RUNBOOK-article-lane.md` §0.

---

## 7. Quy Trình Thực Thi

```text
[Bắt đầu phiên mới]
       │
       ▼
[Bước 1] Chạy trọn 14 hạng mục trong MỘT run_code (0 token)
       │
       ├── ĐỎ ở A1/A2 ──► Conductor sửa được (junction/settings.yaml)
       │                  └─► hiệu lực chỉ sau RESTART
       ├── ĐỎ ở A3 ────► 🔴 DỪNG. Người vận hành PHẢI restart host.
       │                  Không có đường vòng. Báo rõ hai mốc thời gian.
       ├── ĐỎ ở A4 ────► 🔴 DỪNG. Người vận hành PHẢI mở lại phiên
       │                  với preset News-Scape Conductor.
       ├── ĐỎ ở B1/B2 ─► Conductor TỰ sửa: build_article_prefix.py
       │                  → dán persona → --check-preset → QUAY LẠI A3
       ├── ĐỎ ở C1/C2 ─► người sửa settings.yaml (cần restart) / đổi permission phiên
       ├── ĐỎ ở C3 ────► 🔴 DỪNG NGAY. Sửa code, không được chạy.
       └── ĐỎ ở D3/D4 ─► người quyết chạy ngày nào / 🟡 đóng phiên, mở phiên mới

[Tất cả XANH] ──► Đủ điều kiện gõ lệnh đợt
```

**Điểm quay lui bắt buộc:** sửa preset (B2) **luôn** kéo theo nhu cầu restart (A3). Sau khi dán persona **phải quay lại kiểm A3** trước khi kết luận XANH. Bỏ bước này là bỏ đúng bước quan trọng nhất.

---

## 8. Neo Tham Chiếu

- [`.agents/skills/dsh-preflight-validator/SKILL.md`](../skills/dsh-preflight-validator/SKILL.md) — checklist đầy đủ và mẫu lệnh gộp
- [`.agents/dsh/RUNBOOK-article-lane.md`](../dsh/RUNBOOK-article-lane.md) §0 (chuẩn bị một lần)
- [`.agents/dsh/DSH-VIEC-THU-CONG.md`](../dsh/DSH-VIEC-THU-CONG.md) — việc chỉ làm được bằng tay
- [`.agents/dsh/README.md`](../dsh/README.md) — cảnh báo live-reload khi host đang chạy
- [`08-context-and-zero-probe-guardrails.md`](08-context-and-zero-probe-guardrails.md) — kỷ luật ngữ cảnh của phiên điều phối

> **Cảnh báo về tài liệu:** đừng tin tài liệu, tin lệnh kiểm. Kiểm ngày 21/09 cho thấy `DSH-VIEC-THU-CONG.md` mục 2 và 7 viện dẫn sai cả `ptc` lẫn `high`.