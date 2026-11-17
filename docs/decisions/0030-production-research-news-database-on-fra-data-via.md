---
id: ADR-0030
type: adr
title: Production Research news lakehouse on FRA Data with gated daily partitions and Research slots
status: proposed
lane: high-risk
created: 2026-11-10
updated: 2026-11-11
lang: en
authors: [claude]
approvers: []
story: []
supersedes: []
amends: [ADR-0023]
evidence:
  - "path: project/src/research_db/"
  - "path: project/scripts/research_publish.py"
  - "test: project/tests/test_research_production.py"
  - "metric: real-data trial 2026-11-10, 45592 DoD candidates, 45580 admitted, 12 rejected, 440 partitions, 48 MB, first publish 30 s, unchanged publish 2.2 s writing 0 files"
  - "metric: plugin fpts-market-intel on production layout, init 1.3 s, range 0.4 s, entity query 2.1 s"
  - "metric: DuckDB 1.5.6 holds a Parquet file during a query; os.replace fails with WinError 5"
summary: Publish only fully processed articles to FRA - Data/news in the ADR-0023 Parquet layout, rewriting changed day partitions at five Research slots plus urgent express pushes; the folder holds data only.
summary_vi: Xuất bản chỉ tin đã xử lý trọn vẹn lên FRA - Data/news theo bố cục Parquet của ADR-0023, ghi lại phân vùng ngày thay đổi tại năm khung giờ Research và đẩy nhanh tin khẩn; thư mục chỉ chứa dữ liệu.
---

# ADR-0030 — Production Research news lakehouse on FRA Data with gated daily partitions and Research slots

## Context

- ADR-0023.D1 forbids writes to the official site `FRA - Data`; the Research team now needs a production news dataset there.
- ADR-0023 already rejected a monolithic SQLite file on OneDrive. A first draft of this ADR repeated that design; review measured 190 to 410 MB per publish and about 1.6 GB a day of recycle-bin growth, so the draft was dropped.
- The sandbox OBT mixes unprocessed rows (`RAW`, `L1_ONLY`) and does not exclude code-first entity rows, so it cannot serve as production.
- Measured on 2026-11-10: the gated set is 45,580 articles; one day partition without full text is about 1.1 MB; weekdays bring 900 to 1,400 articles.
- DuckDB keeps a Parquet file open during a query, so an in-place replace can collide with a reader.
- The sandbox adapter answered a locked target by writing a timestamped side file. A glob reader would count that file as a second copy of the partition.

## Decision

1. D1. `FRA - Data/news` MUST hold data only: `parquet/articles/year=YYYY/month=MM/part-YYYYMMDD.parquet` in the 22-column ADR-0023 OBT schema, and `_manifest/latest.json` listing every partition with rows, size and SHA256. Scripts, readers, locks, logs and probes MUST NOT write there.
2. D2. An article MUST enter production only when its newest DoD-passed content analysis and its DoD-passed, non-code-first entity analysis both exist and the record passes field validation (`research-gate/1`). Full article text is not published.
3. D3. The writer keeps its state in a local master (`<data_root>/research_db`). Each publish rewrites only the day partitions the gate touched; identical bytes are skipped. The manifest is written last.
4. D4. Writes to production MUST use the lakehouse adapter in strict mode: retry a locked target, then fail and keep the day queued. A side file is never written.
5. D5. Publishing runs in `ops_daemon` at five slots every day: 07:50, 08:45, 12:50, 15:50 and 17:50. Each slot follows a flush window and waits up to 15 minutes for a running wave. Missed slots collapse into one catch-up publish; urgent articles trigger an express publish at most every 30 minutes.
6. D6. A sync that would retract more than 5% of production MUST abort. A missing, resized or unindexed partition MUST be rebuilt from the master on the next publish.
7. D7. Consumers read through the `fpts-market-intel` plugin, which prefers `FRA - Data/news` over the sandbox.

## Alternatives

| Option | Why rejected |
|---|---|
| A. Immutable SQLite generations with a pointer | 190 to 410 MB per publish and recycle-bin growth near 1.6 GB a day; repeats what ADR-0023 rejected. |
| C. Base files plus immutable delta files and manifest-driven reads | Needs tombstones, article-level dedupe and a new reader on every analyst machine; old months still need rewrites for late articles. Revisit if D4 retries or version history become a problem. |
| D. SQLite delta files merged locally | Custom merge logic and a second client stack beside the plugin. |

## Consequences

- Gains: the plugin and its skills work unchanged; an unchanged slot writes nothing; a normal slot rewrites one or two partitions of about 1 MB.
- Cost: SharePoint keeps version history of rewritten day partitions, estimated at 3 to 6 MB a day.
- Risk: early slots carry little new data while waves start after 09:00; the machine must run from about 06:45.
- Twelve DoD-passed `agent-output-v1` records lack `key_points` and `sentiment`; they stay out until re-analysed.

## Rollback

Set `research_publish.enabled: false` in `config/ops.yaml` and restart the daemon; the operator may then empty `FRA - Data/news`. Reverting `project/src/research_db/` removes the capability; the sandbox lakehouse is unaffected.

## Follow-up

- [ ] Human approval of this ADR.
- [ ] Set `NEWS_SCAPE_RESEARCH_DB_DIR`, enable `research_publish`, restart `news-scape-ops`, run the first publish.
- [ ] Set SharePoint permissions on `FRA - Data/news` to read-only for the Research team.
- [ ] Redistribute the `fpts-market-intel` plugin with the production-first discovery.
- [x] Capture completeness after outages (2026-11-11, rule 10 §3). New reference channels cover thoibaotaichinhvietnam, vietstock and vietnambiz. The reconcile window grows with the outage, and the fireant and cafef APIs page back to a cutoff. Other parts: the `capture_channels` probe, publication times for URL backfills, `lookback_days: 3` and backlog rule T4.
- [ ] baodautu monthly sitemap broken on the publisher side since 2026-10-23; listing pagination is its only channel until fixed.
