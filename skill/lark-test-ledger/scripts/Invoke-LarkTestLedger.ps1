[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$ProjectRoot = (Get-Location).Path,
    [string]$EnvFile,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$LedgerArgs
)

$ErrorActionPreference = 'Stop'
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
if (-not $EnvFile) {
    $EnvFile = Join-Path $resolvedProject '.lark-test-ledger\ledger.env'
}
if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Project ledger config not found: $EnvFile. Run Setup-LarkTestLedgerProject.ps1 first."
}
$resolvedEnv = (Resolve-Path -LiteralPath $EnvFile).Path
$runtime = Join-Path $PSScriptRoot 'lark-test-ledger.pyz'
if (-not (Test-Path -LiteralPath $runtime)) {
    throw "Skill runtime not found: $runtime"
}
$pythonCommand = Get-Command python -ErrorAction Stop
$env:PYTHONUTF8 = '1'
& $pythonCommand.Source $runtime --env-file $resolvedEnv @LedgerArgs
exit $LASTEXITCODE
