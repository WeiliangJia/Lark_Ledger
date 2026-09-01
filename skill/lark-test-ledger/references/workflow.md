# Lark test ledger workflow

## Contents

- Configuration
- Generation and synchronization
- Execution and evidence
- Troubleshooting

## Configuration

Use `scripts/Setup-LarkTestLedgerIdentity.ps1` once per Windows user. Use `scripts/Setup-LarkTestLedgerProject.ps1` once per project. The project config references the shared identity; it never contains App Secret or token values.

Run `scripts/Invoke-LarkTestLedger.ps1 doctor` after setup. `authorized`, `target_accessible`, and `schema_ready` should be true. If Schema is incomplete, run `schema plan` and inspect it before `schema apply`.

## Generation and synchronization

Manifest Schema versions `lark-test-ledger/v1` and legacy `dms-test-ledger/v1` are accepted. Each Manifest must contain source hashes, requirements, globally unique cases, at least one contiguous submission order, and `meegle_feature`.

```powershell
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' validate '.\cases\manifest.json' --verify-sources
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' sync '.\cases\manifest.json'
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' sync '.\cases\manifest.json' --commit
```

The first sync command is a dry-run. Definition synchronization reports stale records but does not delete them, and it preserves execution results, notes, people, dates, and attachments.

## Execution and evidence

```powershell
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' case list --submission-only
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' execution next
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' execution record --case-id 'TC-001' --result passed --notes '符合预期'
& '<skill-root>\scripts\Invoke-LarkTestLedger.ps1' execution record --case-id 'TC-002' --result failed --notes '保存时报错' --evidence '.\evidence\TC-002.png'
```

Failed results require evidence or an explicit evidence-unavailable reason. Attachments are appended, not replaced. The command rereads the record and verifies the write.

## Troubleshooting

- Missing global identity: run `Setup-LarkTestLedgerIdentity.ps1`.
- Missing project config: run `Setup-LarkTestLedgerProject.ps1` with the full Base URL.
- Browser does not open: use the authorization URL printed in the terminal.
- Callback timeout: confirm `http://127.0.0.1:8765/callback` is registered and port 8765 is free.
- Base access failure: confirm the OAuth user is a Wiki/Base member with edit permission and the App version/scopes are published.
- Token expiry: rerun identity setup without `-SkipAuth` or invoke `auth` using a configured project.
