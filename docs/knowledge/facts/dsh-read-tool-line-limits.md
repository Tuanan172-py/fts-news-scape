---
id: FACT-dsh-read-tool-line-limits
type: fact
title: DSH read tool line and byte limits
status: active
created: 2026-09-18
updated: 2026-10-06
verified: 2026-10-06
lang: en
authors: [claude-opus-5-5]
adr: []
evidence:
  - "path: project/src/agent/distill.py"
  - "path: project/scripts/article_pack.py"
  - "path: .agents/dsh/RUNBOOK-article-lane.md"
summary: The DSH read tool truncates lines over 2,000 characters, so packets keep every line under that cap by splitting paragraphs and writing indent=1 JSON, never compact JSON.
---

# FACT-dsh-read-tool-line-limits — DSH read tool line and byte limits

## Fact

- `dsh-tool-fs` limits: `readMaxLineLength` 2,000 characters per line, `readMaxBytes` 51,200 bytes per call, `readLimit` 2,000 lines per call.
- The early plan rule "compact JSON is mandatory" was wrong. Compact JSON put a whole packet on one line of 267K characters and lost 99.3% of the content.
- The correct rule: no line exceeds the cap. Packets split content into a paragraph array and are written with `indent=1`.
- `split_long_paragraph` in `project/src/agent/distill.py` splits a long paragraph at sentence boundaries instead of dropping it.
- `MAX_PARAGRAPH_CHARS` is 1600 in the repo on 2026-10-06; the 2026-09-21 memory recorded 1800.
- A 100-article batch weighs about 348KB and needs 7 to 8 paged reads. They run inside one program, so they add no model step.
- Measured on 2026-09-21 over 14,199 real lines: exactly one line exceeded the threshold, the longest at 2,059 characters.

## Why

- Earlier `agent_export.py` and `batch_handoff.py` wrote `indent=2` packets whose `cleaned_text` lines reached 2,173 to 2,537 characters.
- The agent then stopped trusting what it read and opened 15 Grep rounds to verify citations; a 5-article Gold run cost 154K to 300K tokens.
- Citations by paragraph index remove the need for the model to verify quotes itself.

## How to Apply

- Any new packet writer MUST keep every line under 2,000 characters.
- MUST NOT write packets as single-line compact JSON.
- Re-measure the longest packet line after changing distillation or packing.
