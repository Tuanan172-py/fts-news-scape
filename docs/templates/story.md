# US-XXX — <short title>

- **Status:** planned | in_progress | implemented | changed | retired
- **Lane:** tiny | normal | high-risk
- **Parent / Epic:** <free text, e.g. "Phase 3 — Gold / agent-extract"> <!-- Epic surrogate; no epic folders at H1 -->
- **Intake date:** YYYY-MM-DD
- **Depends On:** <US-YYY, or none>

## Product Contract
<What must be true when done, from the user/consumer's view. Link OKF docs (project/docs/skills/*, design/*).>

## Acceptance Criteria
- [ ] <observable criterion 1>
- [ ] <observable criterion 2>

## Design Notes
<Smallest real slice. Which project/src module. What NOT to do. Boundary respected (Silver = pure fn of Bronze, etc.).>

## Validation
| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `cd project; python -m pytest tests/...` | not run | |
| Integration | | — | |
| E2E | | — | |
| Platform | | — | |

> "No proof = not implemented." Set a tier to passed only after the command ran and output is recorded.

## Harness Delta
<Any backlog entry / decision / doc created because of this story. "none" only after checking.>

## Evidence
<Paste command output / file paths / commit hash proving each passed tier.>

## Trace (inline, H1)
- **Actions:** <a, b, c>
- **Files read:** <...>
- **Files changed:** <...>
- **Outcome:** completed | blocked | partial | failed
- **Friction:** <specific pain + missing capability, or "none">
