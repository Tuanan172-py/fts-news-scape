---
id: FACT-opencode-install-layout
type: fact
title: opencode install layout on the operator machine
status: active
created: 2026-10-01
updated: 2026-10-06
verified: 2026-10-01
lang: en
authors: [claude-opus-5-5]
adr: []
evidence:
  - "operator: 2026-10-01 opencode upgraded from 1.2.6 to 1.18.34 and workspace.project_id column added"
summary: The first opencode on the user PATH is a hand-copied binary that npm does not update; FreeTierError means an old client; opencode2 is a third-party fork.
---

# FACT-opencode-install-layout — opencode install layout on the operator machine

## Fact

- `C:\Users\anpt\AppData\Local\opencode-cli\opencode.exe` is first on the user PATH. It is a hand copy of `%APPDATA%\npm\node_modules\opencode-ai\node_modules\opencode-windows-x64\bin\opencode.exe`.
- `npm i -g opencode-ai@latest` does not update that copy; copy it again. The old 1.2.6 build is kept as `opencode-1.2.6.exe.bak`.
- `AppData\Local\opencode\` is the Desktop app 1.2.6 (2026-02); its `opencode.cmd` points to the opencode-cli copy.
- The error "OpenCode's free tier can only be used from within OpenCode" (FreeTierError) means the client is too old for new free models. Upgrading fixed it (2026-10-01: 1.2.6 to 1.18.34).
- `opencode2` (npm, v2.2.0) is a third-party fork (repo game-libgdx-unity/opencode2, maintainer thanhvinh1), not the official build.
- `opencode2` uses its own data in `~/.config/opencode2` and `~/.local/share/opencode2`, carries no `auth.json`, and cannot load the Orca plugin.
- `Documents\WindowsPowerShell\profile.ps1` once held `Set-Alias opencode/opencode2` pointing at the Desktop `opencode-cli.exe` 1.2.6. It was removed on 2026-10-01.
- On 2026-10-01, `opencode` 1.18.34 failed in every git folder with "Unexpected server error / no such column: project_id".
- Cause: `~/.local/share/opencode/opencode.db` had a v2-style `workspace` table, while `Project.migrateProjectId` runs `UPDATE workspace SET project_id`.
- Fix: `ALTER TABLE workspace ADD COLUMN project_id text` on the empty table. DB backup: `%TEMP%\opencode.db.bak-20261001`.

## Why

- Several opencode builds coexist on this machine, so the binary that runs depends on shell, PATH order and profile aliases.
- The errors look like account or server problems but are local version or schema drift.
- The issue is unrelated to `ORCA_*` variables.

## How to Apply

- If PowerShell reports a different version than cmd or bash, check profile aliases first.
- After an npm upgrade, copy the new binary into `opencode-cli`.
- If the `project_id` error returns after another v2 client writes the DB, add the column again.
