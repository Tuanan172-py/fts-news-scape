# Rebuttal 3: ops and governance red team (Round 3)

## 1. Prompt injection
- **Neither design is enough on its own.** D1's empty cwd guards nothing, because the global allow rule `command(regex:.*\.py$)` also matches absolute paths to repo scripts (spike1 finding 6). Detecting a tool call after it ran is forensics.
- **D2's sandboxed profile is the real prevention.** Use it with an empty allowlist for one-shot and a PreToolUse deny-all hook that fails closed.
- **Mandatory for every call:**
  - regenerate and hash-check the profile (agy rewrites settings.json);
  - assert that cli.log contains `loaded 1 named hooks`;
  - run D1's VIOLATION classifier;
  - treat `denied_actions` as FATAL.
- **Residual risk:** injected text can still steer content. Only the validators and DoD catch that.

## 2. Gates before `--finish`
1. The `i` set equals the packet exactly: no duplicates, none missing.
2. `e[1]` is one of the 11 codes. `e[0]` is verbatim in the title or `p[]` (non-IND).
3. `c` is in range with at least 2 distinct indices. Enums and lengths pass.
4. **Diacritics:** reject a record if the source has diacritics and `s`/`im` has none.
5. `meta.json` exists, its `core_sha` equals the prefix hash, and the wave uses one runner.
6. **"Corrupted" (hỏng) = parse failures + validator rejects + dropped fields.** Above 10%, stop the wave. D1's silent field-dropping violates ADR 0008 §2.4 unless it is counted.

## 3. Batch size
50 for agy, 100 for DSH, as a per-runner default. Going to 100 saves only 8% and doubles what a #902 cancellation or schema retry loses.

## 4. MCP repair lane
**Defer it, with no registry entry.** WIP=1 applies, it needs its own Rule 01 §1 exception, and `--repair` already covers missing `i`s. Log it as a `backlog` item and reopen it if repair or cancellation stays above 5% across 5 waves.

## 5. Sequence
0. Intake #25. ADR 0010 `proposed`. Register 0008/0009 in the `decision` table.
1. **US-025 (normal):** fail-loud ingest (`check=False`), one shared `.pipeline.lock`, retire news_cron, assert the DB path.
2. **H1:** accept ADR 0010, including ToS and data-egress sign-off.
3. **US-026 (high-risk):** `--runner agy` at L0 with the profile, validators, provenance and ledger `runner`. Run a 200-article A/B; it passes at DoD ≥99% and parse_fail <2%.
4. **US-027 (high-risk):** tick, standing order and quota guard at L1. **H2:** the operator writes the standing order.
5. **H3:** promote L1 to L2 after 5 clean waves.

## 6. Where D1/D2 break my ops shell
- **D1's `.article.lock` is a second lock.** It doesn't exclude `run_daily`, so use one lock only.
- **D1's pin-drift → FATAL,** combined with self-updates (1.2.7 → 1.2.9 in 2 days), makes the lane go dark regularly. It needs a dead-man alert and a re-pin runbook.
- **D2's `HOME`/`USERPROFILE` override** must apply to the agy child only. The tick passes `MONOCLE_DB_PATH` explicitly. Keyring auth means Task Scheduler must stay "Interactive only".
- **Per-call `llm_trace` rows go to local disk.** harness.db lives in OneDrive, so write only per-wave summaries there.
- **Use one local root,** `C:\data\news-scape`.
- **Quota is metered in "Work Done" units, not tokens.** L1 has to calibrate the token proxy (about 2.2M tokens per 1,000 articles).
- **QUOTA needs a persisted breaker.** Otherwise every slot hits the quota wall again.
- **I accept D1's three slots,** as long as they add catch-up coalescing and a backlog predicate.
