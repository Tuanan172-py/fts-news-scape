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

Preset được nạp qua **root cấu hình**, KHÔNG qua junction:

```powershell
# Dừng host dsh web trước. Sửa khi host đang chạy gây live-reload phá tool catalog.
# Ghi nội dung .agents/dsh/patch/web.cordis.patch.yml vào:
#   %DSH_HOME%\profiles\web\cordis.patch.yml   (bản đang nạp vẫn là [] — chưa áp thì preset không bao giờ hiện)
# Rồi khởi động lại host.
```

Root là `<repo>\.agents\dsh\presets` — thư mục **thật** chứa `news-scape-conductor/` là thư mục con **thật**.

**Vì sao KHÔNG dùng junction:** `dsh-agent-presets` quét root bằng `readdir(dir, { withFileTypes: true })` rồi lọc `if (!child.isDirectory() || !PRESET_ID.test(child.name)) continue;` (`dsh-agent-presets/lib/types/discovery.js:293`). Trên Windows một junction được `readdir` báo là **symlink** (`isDirectory === false`, `isSymbolicLink === true`) nên **bị bỏ qua im lặng** — preset không hiện trong picker, không kèm lý do "broken", không có lỗi nào để đọc. Junction là đường cụt; đã kiểm chứng trên máy 2026-09-18.

**Cảnh báo:** sửa `%DSH_HOME%\profiles\web\cordis.patch.yml` khi host đang chạy gây live-reload phá tool catalog của phiên. Chỉ áp khi host đã dừng, rồi khởi động lại.

**Patch ghi đè TOÀN BỘ config của row**, nên phải restate đủ trường (`default`, `roots`), không chỉ trường muốn đổi.

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
