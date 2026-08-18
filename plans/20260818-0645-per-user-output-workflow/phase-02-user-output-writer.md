# Phase 02 — Per-User Output Writer (CSV theo ngày, gate "đủ layer")

## Context links
- Parent: [plan.md](plan.md) · Scout: [scout-01-db-pipeline.md](scout/scout-01-db-pipeline.md)
- Depends: Phase 01 (subscriptions). Reuse `csv_export.write_csv`, `EntityRegistry.subscribers_for`.

## Overview
- **Date:** 2026-08-18 · **Priority:** P0 · **Impl status:** ⬜ · **Review:** ⬜
- Với mỗi article đã đủ 2 layer (DoD-pass), tìm user đăng ký entity liên quan → ghi CSV per user/ngày.

## Key Insights
- Gate = `l1_outputs.dod_pass=1` AND `agent_outputs.dod_pass=1` cho cùng article_id.
- Entity của article lấy từ `l1_outputs.output_json.entities[]` (in_list=true → entity_id) — chính xác hơn `articles.symbols`.
- `subscribers_for(entity_set)` trả set user chạm tới → chỉ ghi cho user đó → tránh scan chéo.
- 3 file/ngày để tránh I/O coupling: `L1.csv`, `agent.csv` (dump từng layer), `final.csv` (gated join, DELIVERABLE). Ghi atomic (temp + os.replace).

## Requirements
1. Query articles có cả 2 layer done trong khoảng ngày.
2. Map article → users (qua entity set ∩ subscription).
3. Ghi `users/output/<name>/<YYYY-MM-DD>/final.csv` (+ L1.csv, agent.csv).
4. utf-8-sig (Excel-safe). Cột dễ đọc cho analyst.
5. Idempotent: không nhân đôi dòng khi chạy lại (dedupe theo article_id — dùng checkpoint P3).

## Architecture
### Module `project/src/export/user_output.py`
```
class UserOutputWriter:
    def __init__(self, store, registry, output_root="users/output", enabled_users=None)
    def gated_rows(self, date=None, days=None) -> list[Row]:
        # SQL JOIN articles ⨝ l1_outputs(dod_pass=1) ⨝ agent_outputs(dod_pass=1)
        # parse output_json → flatten fields
    def route_rows(rows) -> dict[user, list[row]]:
        # for row: eset = l1 entity_ids; for u in subscribers_for(eset)&enabled: bucket[u].append(row + matched=eset∩sub_u)
    def write(self, date=None, days=None) -> dict[user, count]:
        # per user per date → write final.csv (+ L1.csv, agent.csv) atomically; log "done <user> <date>: N rows"
```
### final.csv columns
`article_id, date, source_domain, url, title, matched_entities, summary, key_points,
implication, impact_area, materiality_score, time_sensitivity, sentiment, event_type, confidence`
- `date` = published_at→date (fallback fetched_at). Partition folder theo `date`.
- `matched_entities` = entity user đăng ký MÀ article chạm (join `;`).
- summary=`summary.abstractive`; key_points=`summary.key_points`(join); implication=`implication.text`;
  impact_area=`implication.impact_area`; materiality_score=`materiality.score`;
  time_sensitivity=`materiality.time_sensitivity`; sentiment=`sentiment.polarity`; event_type=`event_type`;
  confidence=`agent confidence`.
### L1.csv / agent.csv (per layer, per user)
- L1.csv: article_id, date, title, entities(entity_id;type), l1_confidence, categories.
- agent.csv: article_id, date, summary, implication, materiality_score, sentiment, event_type, confidence.
- Mục đích: audit + tránh phải chờ cả 2 mới có gì để xem; final.csv mới là bản gated.

## Related code files
- NEW `project/src/export/user_output.py`
- NEW `project/scripts/write_user_output.py` (CLI: `--date today|--days N`, `--users`)
- READ/REUSE `project/src/export/csv_export.py` (`write_csv` utf-8-sig), `entities.py`, `store.py`
- READ `project/schemas/agent-output-v1.schema.json`, `l1-entity-output-v1.schema.json` (field paths)

## Implementation Steps
1. Add store query `iter_gated_articles(date/days)` (JOIN dod_pass both) hoặc raw SQL trong module.
2. Flatten helpers: `flatten_l1(json)`, `flatten_agent(json)` (an toàn với field thiếu).
3. `route_rows` dùng `subscribers_for`; lọc theo `enabled_users`.
4. `write` atomic per file; tạo thư mục ngày; append-or-rewrite dựa checkpoint (P3).
5. CLI script + log "done".

## Todo list
- [ ] gated query + flatten helpers
- [ ] route_rows (subscribers_for + enabled filter)
- [ ] atomic per-user/date CSV writer (final + L1 + agent)
- [ ] CLI write_user_output.py + logging

## Success Criteria
- Article có cả 2 layer done & chạm HPG → xuất hiện trong `users/output/AnPT/<date>/final.csv`.
- Article thiếu 1 layer → KHÔNG vào final.csv.
- Chạy lại không nhân đôi dòng.

## Risk Assessment
- output_json thiếu field (agent optional) → flatten phải null-safe, không throw.
- article date null → fallback fetched_at; nếu vẫn null → thư mục `unknown-date`.

## Security Considerations
- Chỉ đọc DB nội bộ; đường dẫn user name sanitize (chặn `..`, ký tự lạ) khi tạo folder.

## Next steps → Phase 03 (checkpoint để idempotent/resume).

## Resolved (2026-08-18)
- Gate = `l1_outputs.dod_pass=1 AND agent_outputs.dod_pass=1` (BẮT BUỘC agent-reviewed L1; code-first resolved KHÔNG đủ).
- Chỉ article giao union-subscription mới có agent_outputs → final.csv tự nhiên đã lọc đúng phạm vi.
- `enabled_users` truyền vào writer lấy từ `users/input/manifest.yaml`.
