---
type: Playbook
title: Daily Agent Run — chu kỳ per-user
description: Chuỗi vận hành hằng ngày Vòng 3 — phát packet, chạy agent, ingest + DoD, ghi CSV người dùng.
resource: project/scripts/run_daily.ps1
tags: [operations, agent, per-user, daily, runbook]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: run-daily
    resource: project/scripts/run_daily.ps1
    title: run_daily.ps1
  - id: daily-runbook
    resource: project/docs/operations/daily-runbook-per-user.md
    title: Daily runbook per user
  - id: hierarchy
    resource: project/scripts/run_agent_hierarchy.py
    title: run_agent_hierarchy.py
  - id: prompting
    resource: project/docs/operations/agent-prompting-guide.md
    title: Agent prompting guide
sources_last_checked: 2026-09-07
---

Chuỗi này **tách khỏi** [Morninger](../pipelines/morninger.md): capture/Silver chạy liên tục,
còn Vòng 3 chạy **theo lô** (vài lần/ngày hoặc 1 lần cuối ngày). Idempotent nên chạy trùng vô
hại.[^daily-runbook]

# Đường tắt — `run_daily.ps1`

```powershell
.\scripts\run_daily.ps1 -Mode emit                 # phát packet, dừng lại chờ agent
#   → xử lý packet bằng subagent (.agents/skills/gold-financial-analyst, l1-entity-matcher)
.\scripts\run_daily.ps1 -Mode ingest -Days 30      # nạp output + ghi CSV + báo cáo

.\scripts\run_daily.ps1                            # full, agent stub (smoke test)
.\scripts\run_daily.ps1 -Mode ingest -Date all     # bù toàn bộ backlog
```

Tham số: `-Review missed|all` (phạm vi phát packet L1) · `-ExportLimit N` (0 = tất cả) ·
`-NoCompile` · `-KeepPackets` (giữ packet, mặc định dọn để đỡ đồng bộ OneDrive).

Cuối chuỗi tự chạy `scripts/monitor_daily.py --save-md` → `data/reports/daily/report-<date>.md`.

# Chuỗi thủ công tương đương

```powershell
# 0. khi người dùng đổi danh mục
.venv\Scripts\python.exe scripts\compile_users.py --all

# 1. phát packet
.venv\Scripts\python.exe scripts\l1_route.py --review missed
.venv\Scripts\python.exe scripts\agent_export.py --all

# 2. [AGENT NGOÀI] đọc data/agent_tasks/**, nộp JSON vào
#    data/agent_outputs_l1/  và  data/agent_outputs/

# 3. nạp + chấm DoD + ghi deliverable
.venv\Scripts\python.exe scripts\run_user_workflow.py ^
    --l1-dir data\agent_outputs_l1 --agent-dir data\agent_outputs --date today
```

Chỉ ghi lại output từ dữ liệu đã ingest: `scripts/write_user_output.py --date today`.

# Hai điểm cần agent

| Điểm | Đọc | Prompt | Nộp |
|---|---|---|---|
| **L1** nhận diện thực thể | `data/agent_tasks/l1/*.task.json` | `schemas/l1-entity-instructions-v1.md` | `data/agent_outputs_l1/*.json` |
| **Gold** bóc tách nội dung | `data/agent_tasks/*.task.json` | `schemas/agent-instructions-v1.md` | `data/agent_outputs/*.json` |

Guardrail: subagent chỉ đọc `data/agent_tasks/`, chỉ ghi `data/agent_outputs*/`.

# Nhịp trong ngày

```
LIÊN TỤC  15′ : morninger — capture → Silver → work_items    (tự động)
KHI ĐỔI INPUT: compile_users.py --all                        (người dùng)
THEO LÔ      : l1_route ─► [AGENT L1] ─► l1_ingest
               agent_export ─► [AGENT Gold] ─► agent_ingest
               run_user_workflow --date today → users/output/<user>/<date>.csv
```

Con người chỉ chạm **2 việc**: (a) khai entity trong file đăng ký, (b) kích hoạt agent. Còn lại
là script tất định, cron được.

# Kiểm tra sau khi chạy

```sql
SELECT status, COUNT(*) FROM work_items GROUP BY status;                       -- còn pending?
SELECT SUM(dod_pass), COUNT(*) FROM agent_outputs
  WHERE created_at >= datetime('now','-1 day','localtime');                    -- tỷ lệ pass
```

Xem `users/output/<user>/<date>.csv` và bản audit `users/output/_master/<date>*.csv`.

# Sự cố

| Hiện tượng | Xử lý |
|---|---|
| Nhiều `dod_pass=0` | đọc `dod_reasons`; thường là citation < 20 ký tự hoặc không nguyên văn ⇒ gửi lại cho agent sửa (self-healing) |
| Không có bài nào cho người dùng | kiểm tra file đăng ký tồn tại, manifest bật, và log `orphan` |
| `--date today` ra 0 dòng | chạy `-Days 30` / `--date all` |
| Việc kẹt `claimed` | agent chết giữa chừng — xem truy vấn trong [work_items](../tables/work_items.md) |

# Trạng thái tự động hoá

| Thành phần | Trạng thái |
|---|---|
| capture · Silver · work_packages | ✅ tự động (morninger) |
| l1_route / agent_export / *_ingest / write_user_output | ✅ script tất định, cron được |
| **bước agent gọi LLM** | ⚠️ agent-agnostic, không nhúng trong repo — `run_daily.ps1 -Agent stub` chỉ dùng để smoke test |

[^run-daily]: [run_daily.ps1](project/scripts/run_daily.ps1)
[^daily-runbook]: [Daily runbook per user](project/docs/operations/daily-runbook-per-user.md)
[^hierarchy]: [run_agent_hierarchy.py](project/scripts/run_agent_hierarchy.py)
[^prompting]: [Agent prompting guide](project/docs/operations/agent-prompting-guide.md)
