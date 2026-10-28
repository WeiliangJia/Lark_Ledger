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
    throw "未找到项目配置：$EnvFile。请先运行 Start-LarkTestLedger.ps1。"
}
$resolvedEnv = (Resolve-Path -LiteralPath $EnvFile).Path
$runtime = Join-Path $PSScriptRoot 'lark-test-ledger.pyz'
if (-not (Test-Path -LiteralPath $runtime)) {
    throw "未找到 Skill 运行时：$runtime。请从完整发布包重新安装。"
}
$pythonCommand = Get-Command python -ErrorAction Stop
$env:PYTHONUTF8 = '1'
& $pythonCommand.Source $runtime --env-file $resolvedEnv @LedgerArgs
exit $LASTEXITCODE
