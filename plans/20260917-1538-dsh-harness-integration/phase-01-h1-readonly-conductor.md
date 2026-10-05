# Phase 01 — H1: Conductor read-only (patch.yml)

- Parent: [plan.md](plan.md) · Quyền: **đã được anh phê duyệt read-only trên DB vận hành**
- Token: **0** (chưa spawn LLM) · DB write: **không**
- Chỉ dùng `cordis.patch.yml` + package đã ship — không viết package mới.

## Mục tiêu

Dựng một preset conductor đọc được nguồn chân lý (`pipeline.yaml`, radar) và trả về **stage kế tiếp + lệnh chính xác**, không ghi DB, không tiêu token. Đây là bằng chứng DSH đọc đúng DAG trước khi cho nó spawn agent.

## Deliverable

| File | Vai trò |
|---|---|
| `.agents/dsh/presets/news-scape-conductor/preset.yml` | Metadata preset |
| `.agents/dsh/presets/news-scape-conductor/agent.cordis.yml` | Composition read-only |
| `.agents/skills/dsh-conductor/SKILL.md` | Skill điều phối: đọc DAG, gọi radar, trả next stage |
| `.agents/dsh/patch/web.patch.yml` | Patch profile web: thêm root preset |

## Cấu hình đề xuất (agent.cordis.yml)

```yaml
- id: persona
  name: '@deepseek-ai/dsh-persona'
  config:
    prefix: >-
      Bạn là Conductor read-only của mạng lưới agent News-Scape. Chỉ đọc và đề xuất;
      tuyệt đối không ghi DB, không sửa file, không spawn agent.
    suffix: Working directory: {{cwd}}
- id: agent-instructions
  name: '@deepseek-ai/dsh-agent-instructions'
- id: tool-pwsh
  name: '@deepseek-ai/dsh-tool-pwsh'
- id: tool-fs
  name: '@deepseek-ai/dsh-tool-fs'
- id: tool-fs-search
  name: '@deepseek-ai/dsh-tool-fs-search'
- id: tool-jobs
  name: '@deepseek-ai/dsh-tool-jobs'
- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
- id: tool-ask-user
  name: '@deepseek-ai/dsh-tool-ask-user'
- id: tool-todo
  name: '@deepseek-ai/dsh-tool-todo'
```

Patch profile web (`cordis.patch.yml`) thêm root preset:

```yaml
- id: agent-presets
  name: '@deepseek-ai/dsh-agent-presets'
  config:
    default: news-scape-conductor
    roots:
      - path: .agents/dsh/presets
        trust: project
```

## Cơ chế read-only (thang cưỡng chế)

| Mức | Cách | Trạng thái H1 |
|---|---|---|
| 1 | Skill cấm write/edit/spawn; chỉ chạy radar | có |
| 2 | Không mount `dsh-tool-subagent`, không PTC | có |
| 3 | File sandbox read-only cho preset (nếu deployment hỗ trợ policy theo scope) | xác minh khi implement |
| 4 | Guard `tools.restrict({allow:[read,glob,grep,pwsh]})` | để H3 (cần bundle) |

H1 chấp nhận mức 1–2 vì chưa có runner nào tiêu token và mọi lệnh chạy đều read-only; bằng chứng cứng là DB hash không đổi. Mức 3–4 là deliverable H3.

## Trình tự

1. Tạo preset + skill + patch.
2. Mount; mở phiên DSH chọn preset `news-scape-conductor`.
3. Trong phiên: đọc `.agents/pipeline.yaml` + chạy `pipeline_radar.py status`.
4. Trả về bảng stage kế tiếp + lệnh (không thực thi lệnh ghi).
5. Đo hash `monocle.db` trước/sau, đếm file mới trong `data/`.

## Nghiệm thu

| Tier | Điều kiện |
|---|---|
| Unit | — (không có code Python mới) |
| Integration | Preset mount sạch, không row pending/failed; 16 skill dự án hiện trong catalog |
| **Platform** | Phiên thật: radar exit 0; conductor đề xuất đúng stage kế cho ngày 17/09; **SHA256 `project/data/monocle.db` trước = sau**; 0 file mới dưới `data/` |

## Rủi ro & rollback

- Rủi ro: patch profile hỏng làm web GUI không mount. Rollback: xoá/revert `cordis.patch.yml`; preset nằm ngoài profile nên an toàn.
- Rủi ro: preset root trong OneDrive chậm watcher. Chấp nhận ở H1 (ít file).
