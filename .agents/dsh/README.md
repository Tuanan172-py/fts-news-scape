# .agents/dsh — Gói tích hợp DeepSeek Harness (DSH)

> Nguồn chân lý tác nhân vẫn là `.agents/registry.yaml` + `.agents/pipeline.yaml` + `harness.db`.
> Thư mục này chỉ chứa **lớp trình bày/điều phối DSH** sinh ra quanh chúng.

## Cấu trúc

| Đường dẫn | Vai trò |
|---|---|
| `presets/news-scape-conductor/` | Preset conductor: persona, PTC, `agent_l1`, `agent_gold`, skill |
| `presets/news-scape-conductor/skills/dsh-conductor/` | Skill điều phối (nạp qua `customSkillDirs` của preset) |
| `patch/web.cordis.patch.yml` | Bản nguồn patch profile (dùng khi khởi động host sạch; xem §Wiring) |
| `RUNBOOK.md` | Định hướng thực thi toàn bộ quy trình 17/09 trên Conductor |

## Quyết định đã chốt (2026-09-17)

| # | Nội dung |
|:-:|---|
| D1 | Option A — cognitive agent là subagent in-process (`provider: spawn`) |
| D2 | Đường mặc định dùng DSH; bỏ `agy.exe` khỏi mặc định, giữ làm option (chưa thực thi) |
| D4 | H1–H2 wiring nhẹ; H3–H4 đóng gói bundle local `@news-scape/dsh-harness` |
| D5 | H1 read-only trên DB vận hành; DSH điều phối toàn workflow 17/09 |
| D6 | **Mọi model = `deepseek-flash` (DeepSeek-V41-Flash)**; cấm `deepseek-v4-pro` |

Neo: ADR `0009` · ADR `0008` (cổng + trần token) · `plans/20260917-1538-dsh-harness-integration/plan.md`

## Wiring preset vào DSH

Preset được nạp qua **user preset root** bằng junction (không sửa profile, không gây live-reload):

```powershell
cmd /c mklink /J "$env:USERPROFILE\.dsh\.agent-presets\news-scape-conductor" ^
  "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape\.agents\dsh\presets\news-scape-conductor"
```

DSH quét root này mặc định (`includeUserRoot: true`); discovery đọc lại mỗi lần gọi nên preset mới hiện **không cần restart**.

`patch/web.cordis.patch.yml` là bản nguồn thay thế (root cấu hình qua `dsh-agent-presets.roots`). **Cảnh báo:** sửa `%DSH_HOME%\profiles\web\cordis.patch.yml` khi host đang chạy gây live-reload phá tool catalog của phiên. Chỉ áp khi host đã dừng, rồi khởi động lại.

## Ranh giới 2-I/O

`agent_l1`/`agent_gold` đều khai `toolFilter.allow: [read, write]` — khớp `tools_allowed` trong registry. Mọi tool khác (grep/glob/edit/pwsh/web/skill) biến mất khỏi prompt của con và bị từ chối thực thi. Con đọc skill chuyên trách bằng `read`.

## Trạng thái

| Hạng mục | Trạng thái |
|---|---|
| Preset + skill + junction + D6 registry | ✅ |
| H1/H2 Platform proof | ⏳ chờ phiên GUI |
| H3 bundle + hard gate + generator | ⏸️ hoãn |
| H4 governance | ⏸️ hoãn |

## Thêm agent mới

Theo rule 07 §4: entry `registry.yaml` → skill → stage `pipeline.yaml` → story + proof → KPI. Ở DSH: thêm một row `dsh-tool-subagent` vào preset với `toolName`, `persona`, `agentOptions.model: deepseek-flash`, `toolFilter` đúng ranh giới.
