---
id: ADR-0018
type: adr
title: Silver body for the lane and one citation for one-paragraph articles
status: accepted
lane: high-risk
created: 2026-10-05
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
approvers: [operator 2026-10-05]
story: [US-034, US-036]
amends: [ADR-0010]
related: [ADR-0017]
evidence:
  - commit:a7e9db8
  - commit:0340f64
  - commit:737d8ce
  - wave:W10051122
  - path:project/scripts/article_pack.py
  - path:project/src/agent/silver_source.py
  - path:project/src/agent/runner.py
  - path:project/scripts/article_expand.py
  - path:project/src/agent/dod.py
  - path:docs/OPEN-ITEMS.md
  - metric:W10051122 before fix 499/500 records, L1 500/500, content 360/500, about 140 one-paragraph packets
  - metric:W10051122 after fix L1 500/500, content 500/500, OpenRouter free tier at 0 USD, 2026-10-05 15:30
  - operator:approved direction (a) in session 2026-10-05
original: "commit:0340f64"
reconstructed: 2026-10-06
summary: Packets, the thin filter and work packages read the full Silver body first; stale packets are re-packed from Silver; a truly one-paragraph article needs one citation, marked by citation_basis.
summary_vi: Lane đọc thân bài Silver trước gói RSS; packet cũ được đóng gói lại từ Silver; bài thật sự một đoạn chỉ cần một trích dẫn, có dấu citation_basis.
---

# ADR-0018 — Silver body for the lane and one citation for one-paragraph articles

## Context

- Wave W10051122 reached 499/500 records after 5 repair rounds. L1 coverage was 100%.
- Content coverage reached only 360/500, so `--finish` refused the wave, as designed.
- Measuring the packets showed about 140 articles carrying exactly one paragraph.
- Re-measuring Silver showed that all 500 articles had full paragraphs.
- The packets were built before Silver existed, so they held only a short RSS excerpt. Old citations therefore could not be matched against the new body.

The ADR text records no story; it came from operating wave W10051122. The single-citation rule shipped in commit a7e9db8 labelled US-034. The Silver-first body and the refresh re-pack shipped in commit 0340f64 labelled US-036. It builds on the unified output contract of ADR-0017 and changes how ADR-0010 packets choose the article body.

## Decision

- D1. Packets, the thin filter and work packages MUST read the full Silver body first.
- D2. An old work package rebuilds itself at the next load (work package version 1.1).
- D3. An article that already has a record but an old packet is re-packed from Silver (refresh).
- D4. During expansion each article keeps only the rows of the batch with the newest raw output.
- D5. An article that truly has one paragraph needs only one citation, marked with `citation_basis`.

### Amendment history

- The first accepted text, committed in a7e9db8, was titled "Một trích dẫn là đủ cho bài tin vắn một đoạn văn". It diagnosed the 140 articles as one-paragraph briefs and treated it as a contract ceiling.
- That text decided three things. One valid citation suffices for an article with fewer than 2 citation-length paragraphs. The expander marks such records `citation_basis: "single-paragraph"`, and the DoD gate lowers its threshold only for that mark.
- The third was that `agent-output-v2-lean` lowers `citations` `minItems` to 1, while the semantic default of 2 stays in DoD.
- Commit 0340f64 rewrote the body in place on the same day after Silver was re-measured. The brief diagnosis was wrong; stale RSS-only packets were the cause.
- The single-citation rule survives as D5. The in-place edit predates ADR-0021 and is recorded here instead of being reverted.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep repairing around the old records | Old citations do not occur in the new body, so every repair round fails. |
| Exempt briefs from Gold | Loses summary and implication for about 28% of the wave without fixing the cause. |
| Remove briefs from the verification denominator (first text) | Makes the denominator a two-speed concept that is hard to explain in post-checks and the ledger. |

## Consequences

Gains:

- Citations can be matched because the packet and the gate read the same body.
- Waves stuck on old packets have a way back without new design.

Costs accepted:

- The three earlier repair rounds of W10051122 cost one more run on the new body.
- Version 1.0 work packages must be rebuilt, which costs one Silver read per article.

### Current status (2026-10-06)

- W10051122 completed at 15:30 on 2026-10-05 with L1 500/500 and content 500/500 on the OpenRouter free tier, per `docs/OPEN-ITEMS.md` CON-1 item 12.
- `resolve_body_text` lives in `article_pack.py`, `WORK_PACKAGE_VERSION = "1.1"` in `runner.py`, and `citation_basis` in `article_expand.py` and `dod.py`.
- Waves W10051042 and W10051050 failed on old packets. `docs/OPEN-ITEMS.md` says in one entry that they were released and in another that release still needs confirmation.
- A second draft also numbered 0018, on thin articles, existed at the time. Commit 737d8ce committed it as ADR-0019.

## Rollback

- Return `resolve_body_text` to the old order, with the RSS package first.
- Keep the new packets, because they are correct.
- Anyone with permission to change Article Lane code may do this.

## Follow-up

- [x] Refresh re-pack, re-run and `--finish` W10051122, and confirm coverage of at least 90% (done 2026-10-05, 500/500).
- [ ] Delete old packets once the wave is done so the store does not grow.
- [ ] Measure the share of old packets in the remaining failed waves (W10051042, W10051050).
