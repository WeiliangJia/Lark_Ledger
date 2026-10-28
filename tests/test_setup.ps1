#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $repo ('.local\setup-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$previousCodex = $env:CODEX_HOME
try {
    $env:CODEX_HOME = Join-Path $testRoot 'codex'
    $source = Join-Path $repo 'skill\lark-test-ledger'
    $installed = & (Join-Path $repo 'Install-LarkTestLedgerSkill.ps1') -SourceSkill $source -SkipCompatibilityLink
    if (-not (Test-Path -LiteralPath (Join-Path $installed.skill 'scripts\lark-test-ledger.pyz'))) { throw 'Installer did not copy runtime' }
    $before = (Get-FileHash -LiteralPath (Join-Path $installed.skill 'SKILL.md')).Hash
    try {
        & (Join-Path $repo 'Install-LarkTestLedgerSkill.ps1') -SkipCompatibilityLink | Out-Null
        throw 'Duplicate installation should fail'
    } catch { if ($_.Exception.Message -notlike '*Skill 已存在*') { throw } }
    if ($before -ne (Get-FileHash -LiteralPath (Join-Path $installed.skill 'SKILL.md')).Hash) { throw 'Existing skill changed' }

    # Stub only external identity/OAuth/Base operations; run the real wizard locally.
    $identityScript = Join-Path $installed.skill 'scripts\Setup-LarkTestLedgerIdentity.ps1'
    Set-Content -LiteralPath $identityScript -Value "param([string]`$ReuseIdentityEnv,[switch]`$SkipAuth); [pscustomobject]@{identity_env=`$ReuseIdentityEnv}" -Encoding utf8NoBOM
    $invokeScript = Join-Path $installed.skill 'scripts\Invoke-LarkTestLedger.ps1'
    Set-Content -LiteralPath $invokeScript -Value @'
param([string]$ProjectRoot, [Parameter(ValueFromRemainingArguments=$true)][string[]]$LedgerArgs)
if ($LedgerArgs -contains 'status') {
    if ($env:LEDGER_TEST_AUTH -eq '1') { '{"authorized":false}' } else { '{"authorized":true}' }
}
elseif ($LedgerArgs -contains 'auth') { Set-Content -LiteralPath (Join-Path $ProjectRoot 'auth-called') -Value 'yes' }
elseif ($LedgerArgs -contains 'doctor') {
    if ($env:LEDGER_TEST_UNREADY -eq '1') { '{"ready":false}' } else { '{"ready":true}' }
} else { throw 'Unexpected external action' }
exit 0
'@ -Encoding utf8NoBOM
    $project = Join-Path $testRoot 'project'
    $configDir = Join-Path $project '.lark-test-ledger'
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    $config = Join-Path $configDir 'ledger.env'
    Set-Content -LiteralPath $config -Value 'LARK_BASE_URL=preserve-existing-target'
    $hash = (Get-FileHash -LiteralPath $config).Hash
    $wizard = Join-Path $repo 'Start-LarkTestLedger.ps1'
    $pwsh = (Get-Process -Id $PID).Path
    & $pwsh -NoProfile -File $wizard -ProjectRoot $project -Client Codex -IdentityEnv 'unused-test-identity'
    if ($LASTEXITCODE -ne 0) { throw 'Wizard should pass with ready Base' }
    $env:LEDGER_TEST_UNREADY = '1'
    & $pwsh -NoProfile -File $wizard -ProjectRoot $project -Client Codex -IdentityEnv 'unused-test-identity' *> (Join-Path $testRoot 'unready.log')
    if ($LASTEXITCODE -ne 1) { throw 'Wizard must fail when Base is not ready' }
    & $pwsh -NoProfile -File $wizard -ProjectRoot $project -Client Codex -BaseUrl 'https://example.com/base/other?table=tblother' *> (Join-Path $testRoot 'existing.log')
    if ($LASTEXITCODE -ne 1) { throw 'Wizard must reject implicit target replacement' }
    if ($hash -ne (Get-FileHash -LiteralPath $config).Hash) { throw 'Wizard overwrote project config' }
    Remove-Item Env:\LEDGER_TEST_UNREADY
    $env:LEDGER_TEST_AUTH = '1'
    $freshProject = Join-Path $testRoot 'fresh-project'
    New-Item -ItemType Directory -Path $freshProject | Out-Null
    $identityFile = Join-Path $testRoot 'dummy-identity.env'
    Set-Content -LiteralPath $identityFile -Value '# Test identity: no real credentials'
    & $pwsh -NoProfile -File $wizard -ProjectRoot $freshProject -Client Codex -IdentityEnv $identityFile -BaseUrl 'https://example.com/base/app?table=tbltest'
    if ($LASTEXITCODE -ne 0) { throw 'Fresh project initialization failed' }
    if (-not (Test-Path -LiteralPath (Join-Path $freshProject 'auth-called'))) { throw 'Fresh project did not request OAuth' }
    $freshConfig = Get-Content -LiteralPath (Join-Path $freshProject '.lark-test-ledger\ledger.env') -Raw
    if ($freshConfig -notmatch 'table=tbltest') { throw 'Fresh project lost target URL' }
    if ((Get-Content -LiteralPath (Join-Path $freshProject '.gitignore')) -notcontains '.lark-test-ledger/') { throw 'Local config is not ignored by Git' }
    Get-ChildItem -LiteralPath $repo -Filter '*.ps1' -Recurse | ForEach-Object {
        $parseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$parseErrors) | Out-Null
        if ($parseErrors) { throw ($parseErrors | Out-String) }
    }
    Write-Host 'Setup checks passed: install, duplicate protection, ready/unready wizard, config preservation, syntax.'
} finally {
    $env:CODEX_HOME = $previousCodex
    Remove-Item Env:\LEDGER_TEST_UNREADY -ErrorAction SilentlyContinue
    Remove-Item Env:\LEDGER_TEST_AUTH -ErrorAction SilentlyContinue
    # Keep the isolated test workspace for inspection; no user profile files were changed.
}
