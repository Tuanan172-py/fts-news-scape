---
type: Python Pipeline
title: Article Lane (Vòng 3 — một lượt gọi cho trọn lô)
description: Đường xử lý bài đăng hợp nhất L1 + Gold thành MỘT lượt gọi mô hình cho cả lô, chạy trên harness DSH. Thay đường 2 lớp cũ ở đường mặc định.
resource: project/scripts/article_run.py
tags: [pipeline, agent, article-lane, dsh, token-economy, cache]
status: stable
generated:
  at: 2026-09-21T00:00:00Z
sources:
  - id: run
    resource: project/scripts/article_run.py
    title: Gộp cả đợt vào một lệnh, sinh chương trình điều phối
  - id: pack
    resource: project/scripts/article_pack.py
    title: Đóng gói packet, xếp tầng ưu tiên, dự toán chi phí
  - id: expand
    resource: project/scripts/article_expand.py
    title: Bung bản ghi, cứu từng item hỏng, tra cứu định danh
  - id: prefix-build
    resource: project/scripts/build_article_prefix.py
    title: Sinh prefix tĩnh từ catalog, kiểm hai vế
  - id: prefix-mod
    resource: project/src/agent/prefix.py
    title: Kích thước và tính toàn vẹn của tiền tố
  - id: distill
    resource: project/src/agent/distill.py
    title: Chắt lọc đoạn tất định, bảo toàn nguyên văn
  - id: runbook
    resource: .agents/dsh/RUNBOOK-article-lane.md
    title: Quy trình vận hành một đợt
  - id: workflow
    resource: .agents/dsh/WORKFLOW-article-lane.md
    title: Lưu đồ vận hành — sáu sơ đồ
  - id: plan
    resource: plans/20260918-1651-article-lane-unified/plan.md
    title: Thiết kế và số đo
sources_last_checked: 2026-09-21
---

**Article Lane** gộp hai lớp nghiệp vụ cũ — nhận diện thực thể (L1) và xử lý nội dung (Gold) —
vào **một lượt gọi mô hình cho trọn một lô bài**. Nó là đường mặc định từ 2026-09-18;
[Agent Handoff](agent_handoff.md) hai lớp vẫn gọi được nhưng chỉ để quay lui.[^plan]

Lý do gộp không phải để gọn mã mà là kinh tế: chi phí của phiên điều phối tỉ lệ với **số
bước**, không tỉ lệ với số bài. Hai vệt audit thật cho thấy 19 bước cho 25 tiêu đề tốn ~845.000
token, còn 21 bước cho 5 bài tốn 154.000–300.000. Cắt nội dung một nửa chỉ giảm ~4% hoá đơn;
cắt số bước từ 19 xuống 1 giảm ~93%.[^plan]

# Bốn bất biến

1. LLM **không** đọc tệp, **không** ghi tệp, **không** tra catalog, **không** tự chấm DoD.
2. Code **không** quyết định thực thể hay tóm tắt — chỉ so khớp, tra cứu, bung chỉ số, đo.
3. Ràng buộc nào cưỡng chế được bằng máy thì **không** viết trong prompt.
4. Mọi cấu hình liên quan ranh giới phải được khẳng định ở runtime, không tin YAML.

# Chu trình một đợt

| Giai đoạn | Lệnh | Chi phí | Việc |
|---|---|---|---|
| Chuẩn bị | `article_run.py --wave W --limit N --batch B`[^run] | **0 token** | kiểm prefix hai vế, chắt lọc, xếp tầng, đóng gói packet, dự toán, sinh chương trình điều phối |
| Chạy mô hình | dán `wave_W.conductor.ts` vào **một** lệnh `run_code` | 1 bước điều phối | hâm bộ nhớ đệm nếu từ 2 lô, chạy mọi lô song song, ghi kết quả ra đĩa |
| Vá, nếu thiếu | `article_run.py --wave W --repair`[^run] | **0 token** | đối chiếu bản ghi nhận được với bài đã gửi, đóng gói lại **đúng phần thiếu** |
| Hoàn tất | `article_run.py --wave W --finish`[^run] | **0 token** | bung bản ghi, tra cứu định danh, nạp DB, ghi sổ cái, sinh bàn giao |

Lưu đồ đầy đủ sáu sơ đồ: [`WORKFLOW-article-lane.md`](../../../.agents/dsh/WORKFLOW-article-lane.md).[^workflow]

# Hợp đồng dữ liệu

**Packet vào** — chỉ số cục bộ thay `article_id` sha256, đoạn văn nguyên văn:[^pack]

```json
{"d":"2026-09-18","n":100,"a":[{"i":0,"t":"<tiêu đề>","p":["<đoạn 0>","<đoạn 1>"]}]}
```

**Bản ghi ra** — mười trường ngắn, mã nhóm thay định danh chuẩn:[^expand]

```json
[{"i":0,"e":[["Hòa Phát","COM"]],"s":"<tóm tắt>","k":["<luận điểm>"],
  "im":"<hàm ý>","sn":"pos|neg|neu","ts":"urg|today|week|month|arch","c":[0,2]}]
```

Mô hình phát **chuỗi nguyên văn + mã nhóm**, không phát `entity_id`: việc ánh xạ do resolver
ngoài làm và làm chính xác hơn vì nó có trọn danh mục. Mười một mã nhóm, mỗi mã một thuật toán
tra cứu riêng.[^expand]

Trích dẫn trả về bằng **chỉ số đoạn**, không chép nội dung. Bộ bung đối chiếu `p[k]` phải là
chuỗi con nguyên văn của `cleaned_text` trước khi ghi DB.[^distill]

# Prefix tĩnh và bộ nhớ đệm

Toàn bộ luật, bảng tra nhóm đóng và ví dụ mẫu nằm trong **prefix tĩnh ~6.343 token**, sinh tự
động từ `entities.json` kèm hash.[^prefix-build] Cộng phần harness luôn nối thêm, tiền tố tĩnh
của mỗi request là **~11.143 token** và trúng bộ nhớ đệm từ lượt gọi thứ hai.[^prefix-mod]

Prefix phải **byte-identical** giữa các lượt. Vì persona được dán tay vào preset DSH,
`build_article_prefix.py --check` kiểm hai vế: tệp còn khớp danh mục, **và** persona còn khớp
tệp. Vế thứ hai là vế duy nhất hỏng mà không để lại dấu vết nào ngoài hoá đơn.[^prefix-build]

Chi tiết kinh tế: [References › Kinh tế token](../references/token_economy.md).

# Giới hạn thật đã đo

| Hạng mục | Giá trị | Nguồn |
|---|---:|---|
| `maxTokens` mỗi request | 256.000 | mặc định adapter DSH |
| Cửa sổ ngữ cảnh | 1.000.000 | adapter DSH |
| Trần đọc mỗi lần gọi | 51.200 byte · 2.000 dòng · 2.000 ký tự/dòng | `dsh-tool-fs` |
| Nội dung mỗi bài sau chắt lọc | ~1.542 token | đo 600 bài |
| Bản ghi mỗi bài | ~900 token | đo 400 bản ghi |

Packet ghi **xuống dòng theo từng đoạn** vì công cụ đọc cắt mỗi dòng ở 2.000 ký tự; compact
JSON dồn cả lô vào một dòng 267.143 ký tự và mất 99,3% nội dung.[^pack]

# Vì sao chia lô chỉ theo `--batch`

`--batch` là cổng chia duy nhất. Ngữ cảnh không phải ràng buộc — trăm bài chiếm ~12% cửa sổ kể
cả khi đọc trọn nội dung; ràng buộc thật là trần đầu ra 256.000 token, tức khoảng 280 bài mỗi
lượt. Cơ chế an toàn là **vá sau, không phòng trước**: gửi trọn lô, thiếu bài thì `--repair`
đóng gói lại đúng phần thiếu.[^run]
