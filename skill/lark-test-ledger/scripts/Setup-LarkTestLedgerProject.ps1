[CmdletBinding()]
param(
    [string]$ProjectRoot = (Get-Location).Path,
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,
    [string]$TableName = '测试用例',
    [string]$IdentityEnv,
    [switch]$SkipAuth,
    [switch]$SkipDoctor
)

$ErrorActionPreference = 'Stop'
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
if ($BaseUrl -notmatch '^https://.+[?&]table=[A-Za-z0-9_-]+') {
    throw 'Base 地址无效。请复制包含 table=<table_id> 的 https Base/Wiki 完整地址。'
}
if (-not $IdentityEnv) {
    $pointerFile = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'LarkTestLedger\skill.env'
    if (-not (Test-Path -LiteralPath $pointerFile)) {
        throw "尚未配置本机身份。请运行 Start-LarkTestLedger.ps1。"
    }
    $pointerLine = Get-Content -LiteralPath $pointerFile | Where-Object { $_ -match '^LARK_IDENTITY_ENV_FILE=' } | Select-Object -First 1
    if (-not $pointerLine) { throw "身份指针缺少 LARK_IDENTITY_ENV_FILE：$pointerFile。请用 -IdentityEnv 指定身份文件。" }
    $IdentityEnv = ($pointerLine -split '=', 2)[1].Trim()
}
$resolvedIdentity = (Resolve-Path -LiteralPath $IdentityEnv).Path

$localDir = Join-Path $resolvedProject '.lark-test-ledger'
New-Item -ItemType Directory -Force -Path $localDir | Out-Null
$envFile = Join-Path $localDir 'ledger.env'
if (Test-Path -LiteralPath $envFile) { throw '项目配置已存在。请使用统一入口复用配置；如需更换 Base，请先核实并手动修改 ledger.env。' }
$envLines = @(
    "LARK_IDENTITY_ENV_FILE=$resolvedIdentity",
    '',
    "LARK_BASE_URL=$BaseUrl",
    "LARK_TABLE_NAME=$TableName",
    '',
    'LEDGER_STATE_DB=state.sqlite3',
    'LEDGER_ARCHIVE_DIR=manifests'
)
Set-Content -LiteralPath $envFile -Value $envLines -Encoding utf8NoBOM

$gitIgnore = Join-Path $resolvedProject '.gitignore'
$ignoreEntry = '.lark-test-ledger/'
$existingIgnore = if (Test-Path -LiteralPath $gitIgnore) { Get-Content -LiteralPath $gitIgnore } else { @() }
if ($existingIgnore -notcontains $ignoreEntry) {
    Add-Content -LiteralPath $gitIgnore -Value $ignoreEntry -Encoding utf8NoBOM
}

$invoke = Join-Path $PSScriptRoot 'Invoke-LarkTestLedger.ps1'
$statusText = & $invoke -ProjectRoot $resolvedProject status | Out-String
if ($LASTEXITCODE -ne 0) { throw '无法读取授权状态。请按上方提示检查身份文件和项目配置。' }
$status = $statusText | ConvertFrom-Json
if (-not $status.authorized -and -not $SkipAuth) {
    Write-Host '即将打开 Lark 授权页面。请本人完成登录、MFA 和授权。' -ForegroundColor Cyan
    & $invoke -ProjectRoot $resolvedProject auth
    if ($LASTEXITCODE -ne 0) { throw 'Lark 授权未完成。请重新运行 auth，在浏览器完成登录并检查回调地址。' }
}

$doctor = $null
if (-not $SkipDoctor -and ($status.authorized -or -not $SkipAuth)) {
    $doctorText = & $invoke -ProjectRoot $resolvedProject doctor | Out-String
    if ($LASTEXITCODE -ne 0) { throw '连接检查未通过。请按上方中文提示修复权限或字段，再运行 doctor。' }
    $doctor = $doctorText | ConvertFrom-Json
}

[pscustomobject]@{
    configured = $true
    project = $resolvedProject
    env_file = $envFile
    identity_env = $resolvedIdentity
    authorized = if ($doctor) { $doctor.authorized } else { $status.authorized }
    target_accessible = if ($doctor) { $doctor.target_accessible } else { $null }
    schema_ready = if ($doctor) { $doctor.schema_ready } else { $null }
}
