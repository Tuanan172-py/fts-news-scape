# Harness v2 Research Report: AI-Agent Session Handoff & Process Design

**Date:** 2026-08-17  
**Scope:** Evaluate proposed H1 scaffolding additions for tiny news-scraping team.

---

## 1. Session Handoff for AI Coding Agents

**Finding:** Effective single-pointer handoffs use structured state-of-world files (not prose notes).

Common patterns:
- **CLAUDE.md / AGENTS.md**: Instructions + context bundled; risk drift/staleness over time
- **State files** (SESSION-LATEST.md, memory.txt): Task list, last commit, blockers, current branch
- **Drift-detection tools** (mex, fiberplane/drift): CI-backed validation—markdown anchors bound to code; stale docs block merges

**Best practice**: Single state file (SESSION-LATEST.md) listing:
  - Current task + goal
  - Last PR/commit + branch
  - Known blockers
  - Next immediate action
  
Avoid hand-edited dashboards; they drift. Bind docs to code via CI checks.

---

## 2. Friction-First vs. Up-Front PM Scaffolding

**Evidence against premature scaffolding:**
- [Big Design Up Front anti-pattern](https://randomactsofarchitecture.com/2013/07/08/big-design-up-front-versus-emergent-design/) creates illusion of knowledge when team knows least
- [YAGNI principle](https://builtin.com/software-engineering-perspectives/yagni): "Unnecessary features are friction you drag on every pass"
- Emergent design minimizes rework; tight feedback loops reveal actual needs

**For tiny teams**: Epic/Initiative hierarchy premature at H1. 
- Walking skeleton > ceremony
- Minimal folders; add when friction emerges
- Example: Don't build OKF knowledge base until you need to share context across sessions

---

## 3. Live-State-in-Markdown Anti-Pattern

**Core danger**: Manual status dashboards drift from reality.
- Gradual staleness → loss of trust → ignored docs
- Concurrent edits + lack of automation = inevitable divergence
- [Project dashboards lose sync](https://www.rocketlane.com/blogs/project-management-dashboard), reducing delivery visibility

**Solution**: Move mutable state to SQLite (harness v2 goal).
- Markdown = immutable docs (processes, decisions, retrospectives)
- Database = live facts (task status, blockers, session metadata)
- CI drift-checks ensure docs ≠ code doesn't advance

---

## 4. WIP Limits & Single-Task Discipline

**Sound principle**: [Limit WIP (Work In Progress) to 1 story](https://www.atlassian.com/agile/kanban/wip-limits).
- Reduces context-switching
- Accelerates delivery; makes blockers visible
- Short lead time + high completion rate

**For AI agents**: Enforce strictly—parallel stories confuse agent memory.  
- One task = one context window = no thrashing
- Interrupt handling: document it formally, don't auto-exceed WIP

**Caveat**: Tiny teams need *intentional* discipline, not just process rules.

---

## 5. Verdict: What to Adopt Now vs. Later

**Worth adding NOW (H1):**
- **SESSION-LATEST.md**: Single pointer to task state. Lightweight, proven pattern. Fixes agent handoff drift immediately.
- **One Story In Progress rule**: Enforce via honor system or simple .md checklist.

**NOT worth it yet:**
- Initiative → Epic → Story hierarchy: No friction yet. Add when backlog exceeds 10 items.
- Project Health dashboard (markdown): Anti-pattern. Wait for SQLite in H2.
- OKF knowledge base folder: Premature. Start with single LEARNINGS.md in SESSION-LATEST.

**Unresolved questions:**
- How to detect WIP violation without CI gate? (Possible future: git hook checks for multiple branches)
- Should SESSION-LATEST be repo-root or `.claude/` scoped?
- When does single-machine team need async handoff vs. real-time collab?
