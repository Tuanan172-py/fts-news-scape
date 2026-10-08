---
id: US-013
type: story
title: Radar false-404 detection and Bronze guard rail for enabled domains
status: implemented
lane: normal
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: []
related: [US-011]
evidence: ["commit:0f1a65c", "path:project/scripts/pipeline_radar.py", "test:project/tests/test_orchestrator.py", "metric:7 passed in test_orchestrator.py, 403 suite passed"]
verify: "cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/test_orchestrator.py -q"
original: "commit:0f1a65c"
summary: A test blocks enabling any domain that does not store Bronze, and the radar flags a per-domain 404 spike as a suspected URL structure change.
---

# US-013 — Radar false-404 detection and Bronze guard rail for enabled domains

## Contract

- Enabling a domain that does not store Bronze MUST be blocked by a test.
- A spike of 404s concentrated on one domain MUST be named by the radar as a suspected URL structure change.
- The reader MUST NOT be led to believe the articles were really removed.

## Acceptance Criteria

- [x] `pipeline_radar.py` queries `source_deleted` with `GROUP BY source_domain`.
- [x] A `HIGH` alert fires when one domain has more than 10 articles with 404/410 AND they exceed 30% of that domain's articles for the day, with the command `validate_capture.py <domain>`.
- [x] `test_enabled_domains_must_capture_bronze` fails if an `enabled: true` domain uses a scraper that does not inherit `CaptureMixin`.
- [x] `test_generic_rss_capture_domains_declare_content_selector` fails if a domain using the generic `RssCaptureScraper` lacks `detail.content_selector`.
- [x] The assert message points to `project/docs/dev/03-adding-a-source.md` §2b.
- [x] `validate_capture.py` lists enabled domains skipped because they declare no `capture:`.

## Design Notes

- A guard rail was chosen instead of migrating 15 domains. Each domain needs selector checks on the live site per `03-adding-a-source.md` §2b, real work needed only when re-enabling.
- The guard rail blocks the exact risky moment (someone setting `enabled: true`) at near-zero cost.
- The first version applied to every `CaptureMixin` subclass and raised a false alarm on `fireant`. That source is an API with JSON Bronze, so a CSS `content_selector` is meaningless.
- Dedicated scrapers have defaults verified for their site: cafef `div#mainContent`, vneconomy `#article-editor`, tnck `div.article__body`, baodautu `#content_detail_news`, vietstock.
- Only `rss_capture.py:50` has a guessed default `"article"`, so the assert was narrowed to `RssCaptureScraper`.
- Lesson: a guard rail must match the real risk area, not a class taxonomy.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/test_orchestrator.py -q` | passed, 7; full suite 403 |
| Integration | radar needs the real DB; checked by a manual run | not recorded |
| Platform | none | not run |

## Evidence

- Real RED/GREEN proof: `enabled: true` was set temporarily on `project/config/domains/znews.yaml` (`method: rss`).

```
FAILED tests/test_orchestrator.py::test_enabled_domains_must_capture_bronze
AssertionError: Domain đang bật nhưng KHÔNG lưu Bronze: znews (method=rss).
Xem checklist project/docs/dev/03-adding-a-source.md §2b trước khi bật ...
```

- After revert, `git diff --stat project/config/domains/znews.yaml` was empty and the test went green again (7 passed).
- Trace #47: `score_trace = 1.0`, `score_context = 1.0`. Outcome: completed. Harness delta: none.
