# Phase 03 — H3: Gold + hard gate + đóng gói bundle

- Parent: [plan.md](plan.md) · Token: **flash** · DB write: **có**
- Phụ thuộc: H2 · Đây là mốc **D4: chuyển từ `cordis.patch.yml` sang bundle local**.

## Mục tiêu

1. Thêm `agent_gold`, chạy Gold có kiểm soát token.
2. Biến cổng ADR 0008 từ **policy** (H2) thành **hard-enforce bằng code**.
3. Đóng gói `@news-scape/dsh-harness` + generator từ `registry.yaml`.

## Deliverable

| Thành phần | Đường dẫn | Vai trò |
|---|---|---|
| Bundle local | `.agents/dsh/plugin/` | Đăng ký tool + hook |
| Tool `ns_radar` | plugin | Bọc `pipeline_radar.py status`, output JSON |
| Tool `ns_activate` | plugin | **Cổng cấp quyền**: hiển thị batch/token/effort; trả CONFIRM_REQUIRED |
| Tool `ns_stage` | plugin | Chạy operator allowlist (iterate/ingest/export/deliver) |
| Tool `ns_gate` | plugin | Kiểm DoD trước khi cho stage sau |
| Tool `ns_metric` | plugin | Ghi `harness.db.agent_metrics` |
| Hook guard | plugin | WIP=1 + Gate-before-advance |
| Hook waterfall | plugin | `tools/result` → metric |
| Generator | `scripts/build_dsh_harness.py` | Sinh composition từ registry + pipeline |
| Row `agent_gold` | preset | Gold cognitive |

## Cổng cấp quyền hard-enforce

```text
ns_activate(stage="gold_analyze", batches=2, items=10)
  → { kind: "CONFIRM_REQUIRED", wave: "2 × 5 bài", model: "deepseek-flash",
      est_tokens: 14700, effort: "low", budget: 40000 }
Chỉ khi người dùng trả lời xác nhận qua ask_user_question thì conductor mới gọi
ns_stage(export) rồi spawn agent_gold. Vượt budget → dừng sạch, báo phần đã làm.
```

## Guard

| Guard | Bất biến | Hành vi |
|---|---|---|
| `guard(WIP)` | WIP=1 | Từ chối ns_stage ghi khi có story `in_progress` khác |
| `guard(gate)` | Gate-before-advance | Từ chối gold_export nếu l1_ingest ngày đó chưa green |

## Generator

`scripts/build_dsh_harness.py` đọc `registry.yaml` + `pipeline.yaml`, sinh `.agents/dsh/gen/*.gen.cordis.yml` (header `DO NOT EDIT`); fail loud khi drift. Đây là cơ chế giữ `registry.yaml` là nguồn chân lý duy nhất (rule 07 §2).

## Nghiệm thu

| Tier | Điều kiện |
|---|---|
| Unit | `ns_activate` không có xác nhận → không spawn; vượt budget → dừng sạch |
| Unit | Generator sinh byte-identical cho cùng input; thiếu trường registry → fail loud |
| Integration | Guard gate chặn `gold_export` khi L1 chưa green; guard WIP chặn khi 2 story |
| **Platform** | 1 wave Gold thật: DoD gold pass ≥ 95%; 1 dòng metric; không vượt budget |

## Rủi ro & rollback

- Bundle cài vào profile cần pnpm install trong workspace profile → rủi ro làm hỏng composition. Rollback: gỡ bundle khỏi `dsh.profile.bundles`, quay lại patch.yml.
- Chất lượng Gold trên flash chưa kiểm chứng → chấp nhận pass rate thấp hơn pro, ghi nhận vào metric để quyết định sau.
