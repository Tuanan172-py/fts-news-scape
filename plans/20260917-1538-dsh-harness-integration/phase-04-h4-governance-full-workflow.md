# Phase 04 — H4: Governance + toàn bộ workflow 17/09

- Parent: [plan.md](plan.md) · Token: **flash** · DB write: **có**
- Phụ thuộc: H3 · Đây là mốc "DSH thực thi toàn bộ quy trình công việc ngày 17/09".

## Mục tiêu

Đưa toàn bộ pipeline L1 → Gold → deliver → brief lên DSH, có governance loop, trong giới hạn model flash.

## Phạm vi

1. Kích hoạt các agent đặc nhiệm **trên flash**: `agent_triage`, `agent_dedup`, `agent_brief`, `agent_verifier`, `agent_auditor`.
2. `entity-curator` giữ **deferred** (Tier-3, cần ADR riêng; không chạy pro).
3. Vòng governance: `ns_metric` → `harness_cli propose` → proposal cho người duyệt.
4. Chạy thật toàn workflow 17/09 trên `monocle.db` vận hành (đã được phép), có backup trước.

## Amendment registry bắt buộc (rule 07)

| Agent | Hiện | Đổi thành |
|---|---|---|
| adversarial-dod-verifier | pro | flash |
| daily-brief-synthesizer | pro | flash |
| harness-auditor | pro | flash |
| entity-curator | pro, Tier-3 | giữ draft + deferred; ghi lý do |

## Trình tự toàn workflow

```text
radar → l1_route(resolved, 0 token) → agent_l1 → l1_ingest(gate) → metric
      → [triage] → [dedup] → gold_export → agent_gold → gold_ingest(gate) → metric
      → deliver → [brief]
      → (governance) agent_auditor → propose
```

Mỗi bước cognitive dừng ở `ns_activate` chờ người xác nhận.

## Nghiệm thu

| Tier | Điều kiện |
|---|---|
| Unit | — |
| Integration | Toàn chuỗi chạy trên bản sao DB trước; mọi cổng gate hoạt động; metric đủ cho mỗi agent |
| **Platform** | Chạy thật trên DB vận hành sau backup: hàng đợi L1/Gold giảm; `agent_metrics` có dòng cho từng agent; 0 lần gọi model ngoài flash; `harness_cli propose` sinh proposal |

## Rollback

- Backup `monocle.db` trước lần chạy đầu; nếu sai, khôi phục backup.
- Tắt DSH conductor, quay lại đường thủ công/agy (vẫn giữ như option theo D2).
