---
name: lark-test-ledger
description: Configure and operate a Lark Base test-case ledger for Codex projects, including generating and syncing cases, reading submission cases, recording execution results, and appending failure evidence. Use when the user mentions Lark test cases, test ledgers, submission testing, or asks to set up this workflow in a project.
metadata:
  short-description: Operate Lark-backed test-case workflows
---

# Lark Test Ledger

Use the bundled scripts for deterministic Lark authentication, configuration, reads, and writes. Never print App Secrets, access tokens, refresh tokens, or token database contents.

## Route the request

- For first-time computer authentication or changing the shared identity, run `scripts/Setup-LarkTestLedgerIdentity.ps1`.
- For first-time setup in the current project, collect `LARK_BASE_URL` and optionally `LARK_TABLE_NAME`, then run `scripts/Setup-LarkTestLedgerProject.ps1`.
- For case generation/synchronization, execution, attachments, or diagnostics, run `scripts/Invoke-LarkTestLedger.ps1` with the matching ledger arguments.
- Read [references/workflow.md](references/workflow.md) when generating cases, committing definitions, executing tests, or troubleshooting.
- Read [references/company-setup-guide.md](references/company-setup-guide.md) only for a full installation/configuration explanation.

## Configuration discovery

The shared identity pointer is `%LOCALAPPDATA%\LarkTestLedger\skill.env`. The project config is `<project>\.lark-test-ledger\ledger.env`.

If the project config is missing, ask only for:

1. `LARK_BASE_URL`, including `table=...`;
2. `LARK_TABLE_NAME`, defaulting to `测试用例`.

Do not ask for App ID or App Secret again when the shared identity pointer exists. Do not copy the shared token SQLite into a project.

## Operational invariants

- Treat the configured Base as canonical. Do not create or switch to another Base unless explicitly requested.
- Use globally unique `用例ID` values.
- A non-empty `提测顺序` marks a submission case and defines execution order.
- Before committing generated definitions, validate sources and show a sync dry-run. Commit only when requested or approved.
- Definition synchronization must preserve human execution fields and existing attachments.
- Execution may update only `Date`, `Attachment`, `测试结果`, and `实际结果/备注`.
- For browser-visible failures, append evidence showing the error or incorrect state. If evidence cannot be captured, record the reason.
- Verify result and attachment writes by rereading the same record.
- Never copy one user's OAuth SQLite to another computer. Other testers authorize with their own company account or use an approved centralized credential service.

## Common commands

Run with PowerShell 7 from the target project:

```powershell
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' doctor
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' case list --submission-only
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' execution next
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' sync '.\cases\manifest.json'
```

Resolve `<skill-root>` from this `SKILL.md` location; do not assume the project contains a copy of the runtime.
