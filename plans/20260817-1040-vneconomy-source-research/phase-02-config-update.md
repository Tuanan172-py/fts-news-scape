# Phase 02 — Config Update (config/domains/vneconomy.yaml)

## Context Links
- Template: `config/domains/vietstock.yaml` (parity)
- `scout/scout-01-code-contracts.md` (missing blocks: capture/compliance/content_selector/language)
- Depends on phase-01 (confirmed `content_selector`)

## Overview
- **Date:** 2026-08-17 | **Priority:** High | **Impl status:** Not started | **Review status:** Not reviewed
- **Description:** Rewrite `vneconomy.yaml` to dedicated-scraper parity: `method: vneconomy`, `enabled: true`, add `language`, `detail.content_selector`, `capture`, `compliance` blocks.

## Key Insights
- Dispatch (orchestrator): `REGISTRY.get(cfg["name"]) or REGISTRY.get(f"_{cfg['method']}")`. `method: vneconomy` + `@register("vneconomy")` → name-key `vneconomy` wins over generic `_rss`.
- CaptureMixin `_init_capture` reads `capture.raw_dir` (dflt `data/raw_html`), `capture.min_body_bytes` (dflt 2048), `compliance.respect_robots` (dflt true), `compliance.proxy_rotation`.
- Silver derives everything from bronze → config only drives capture, not silver.

## Requirements
**Functional**
- `name: vneconomy` (must match filename).
- `method: vneconomy`; `enabled: true`.
- `language: vi`.
- `detail.content_selector` = confirmed phase-01 value.
- `detail.max_details_per_cycle: 30` (keep).
- `capture.raw_dir`, `capture.min_body_bytes: 2048`.
- `compliance.respect_robots: true`, `proxy_rotation: false`, `proxies: []`.
- Keep 3 existing feeds.

**Non-functional**
- `rate_limit: 3.0`, `timeout: 30` (keep). robots crawl-delay (1s) applied at runtime by RobotsGate.

## Architecture
Config-only. No code. Orchestrator auto-discovers via `config/domains/*.yaml` filter `enabled: true`.

## Related Code Files
- MODIFY `config/domains/vneconomy.yaml`

## Implementation Steps
1. Set `enabled: true`, `method: vneconomy`.
2. Add `language: vi` after `timeout`.
3. Under `detail`: add `content_selector: "<phase-01 value>"` (e.g. `"div.detail__content, article"`); keep `extract_full: true`, `max_details_per_cycle: 30`.
4. Add block:
   ```yaml
   capture:
     raw_dir: "data/raw_html"
     min_body_bytes: 2048
   compliance:
     respect_robots: true
     proxy_rotation: false
     proxies: []
   ```
5. Update `pitfalls` note: keep content:encoded-absent note; add "detail server-rendered, img direct src on premedia.vneconomy.vn, 1s crawl-delay".
6. Validate YAML parses (`python -c "import yaml,sys; yaml.safe_load(open('config/domains/vneconomy.yaml',encoding='utf-8'))"`).

## Todo List
- [ ] method → vneconomy, enabled → true
- [ ] add language: vi
- [ ] add detail.content_selector (phase-01 value)
- [ ] add capture block
- [ ] add compliance block
- [ ] update pitfalls note
- [ ] YAML lint passes

## Success Criteria
- `config/domains/vneconomy.yaml` parses; keys mirror `vietstock.yaml` structure.
- `python -c "from src.core.config import ...; list domains"` shows vneconomy enabled (or orchestrator picks it up in phase-05).

## Risk Assessment
- **R1:** Selector placeholder committed before phase-01 confirmed → phase ordering enforces confirm-first. Do NOT commit guess.
- **R2:** UTF-8 Vietnamese in feed names → ensure file saved UTF-8 (existing file already UTF-8).

## Security Considerations
- `respect_robots: true` mandatory (robots blocks `/api/`,`/tim-kiem.html?`,`?nocache=true`; RobotsGate enforces + honors 1s crawl-delay). `proxy_rotation: false` (no anti-bot).

## Next Steps
- Feeds phase-03 (scraper reads `content_selector`) + phase-05 (enable/e2e).
