[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [string]$BaseUrl,
    [string]$TableName = '测试用例',
    [string]$IdentityEnv,
    [string]$AppId,
    [string]$AppSecret,
    [string]$RedirectUri = 'http://127.0.0.1:8765/callback',
    [string]$Python = 'python',
    [switch]$ApplySchema,
    [switch]$SkipAuth,
    [switch]$SkipOpenBase,
    [switch]$SkipVenv
)

$ErrorActionPreference = 'Stop'
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$localAppData = [Environment]::GetFolderPath('LocalApplicationData')
if (-not $IdentityEnv) {
    $IdentityEnv = Join-Path $localAppData 'LarkTestLedger\identity.env'
}
$identityPath = [IO.Path]::GetFullPath($IdentityEnv)

if (-not (Test-Path -LiteralPath $identityPath)) {
    Write-Host '首次配置此电脑，需要创建私有 Lark 身份配置。' -ForegroundColor Cyan
    if (-not $AppId) {
        $AppId = Read-Host '请输入公司自建 Lark App ID'
    }
    if (-not $AppSecret) {
        $secureSecret = Read-Host '请输入公司自建 Lark App Secret（输入会隐藏）' -AsSecureString
        $AppSecret = [Net.NetworkCredential]::new('', $secureSecret).Password
    }
    if (-not $AppId.Trim() -or -not $AppSecret) {
        throw 'App ID and App Secret must not be empty'
    }
    $identityDir = Split-Path -Parent $identityPath
    New-Item -ItemType Directory -Force -Path $identityDir | Out-Null
    $tokenDb = Join-Path $identityDir 'oauth.sqlite3'
    $refreshLock = Join-Path $identityDir 'oauth-refresh.lock'
    $identityLines = @(
        "LARK_APP_ID=$($AppId.Trim())",
        "LARK_APP_SECRET=$AppSecret",
        "LARK_REDIRECT_URI=$RedirectUri",
        'LARK_OAUTH_SCOPES=offline_access bitable:app wiki:node:read auth:user.id:read',
        '',
        "LARK_TOKEN_DB=$tokenDb",
        "LARK_OAUTH_LOCK_PATH=$refreshLock",
        'LARK_BATCH_SIZE=200',
        'LARK_REQUEST_TIMEOUT=30'
    )
    Set-Content -LiteralPath $identityPath -Value $identityLines -Encoding utf8NoBOM
    $AppSecret = $null
    $secureSecret = $null
    Write-Host "已创建私有身份配置：$identityPath" -ForegroundColor Green
} else {
    $identityPath = (Resolve-Path -LiteralPath $identityPath).Path
    Write-Host "复用已有私有身份配置：$identityPath" -ForegroundColor Green
}

if (-not $BaseUrl) {
    $BaseUrl = Read-Host '请输入项目 Lark Base/Wiki 完整地址（必须包含 table=...）'
}
if ($BaseUrl -notmatch '^https://.+[?&]table=[A-Za-z0-9_-]+') {
    throw 'BaseUrl must be an https URL containing table=<table_id>'
}

$initializer = Join-Path $PSScriptRoot 'Initialize-LarkTestProject.ps1'
if (-not (Test-Path -LiteralPath $initializer)) {
    throw "Initializer not found beside setup wizard: $initializer"
}
$initArgs = @{
    ProjectRoot = $resolvedProject
    BaseUrl = $BaseUrl
    SharedIdentityEnv = $identityPath
    TableName = $TableName
    Python = $Python
}
if ($SkipVenv) { $initArgs.SkipInstall = $true }
& $initializer @initArgs | Out-Host

$localDir = Join-Path $resolvedProject '.lark-test-ledger'
$launcher = Join-Path $localDir 'lark-ledger.ps1'
$agentsTemplate = Join-Path $PSScriptRoot 'AGENTS.md.template'
$agentsText = (Get-Content -LiteralPath $agentsTemplate -Raw).Replace('${LARK_BASE_URL}', $BaseUrl)
$projectAgents = Join-Path $resolvedProject 'AGENTS.md'
if (-not (Test-Path -LiteralPath $projectAgents)) {
    Set-Content -LiteralPath $projectAgents -Value $agentsText -Encoding utf8NoBOM
    Write-Host "已创建项目 Codex 指令：$projectAgents" -ForegroundColor Green
} else {
    $snippet = Join-Path $localDir 'AGENTS.lark-test-ledger.md'
    Set-Content -LiteralPath $snippet -Value $agentsText -Encoding utf8NoBOM
    Write-Warning "项目已有 AGENTS.md。请把 $snippet 的内容合并进去，避免覆盖原规则。"
}

$statusText = & $launcher status | Out-String
if ($LASTEXITCODE -ne 0) { throw 'Unable to read local authorization status' }
$status = $statusText | ConvertFrom-Json
if (-not $status.authorized -and -not $SkipAuth) {
    Write-Host ''
    Write-Host '即将自动打开 Lark 授权页面。请在浏览器中登录公司账号并确认授权。' -ForegroundColor Cyan
    Write-Host '脚本不会读取或保存你的 Lark 登录密码/MFA。' -ForegroundColor Cyan
    & $launcher auth
    if ($LASTEXITCODE -ne 0) { throw 'Lark OAuth authorization failed' }
} elseif (-not $status.authorized) {
    Write-Warning "尚未授权。稍后运行：& '$launcher' auth"
}

$doctor = $null
if (-not $SkipAuth -or $status.authorized) {
    $doctorText = & $launcher doctor | Out-String
    if ($LASTEXITCODE -ne 0) { throw 'Lark connection doctor failed; review the preceding error' }
    $doctor = $doctorText | ConvertFrom-Json
    if (-not $doctor.schema_ready) {
        if ($ApplySchema) {
            Write-Host '正在补齐测试账本 Schema……' -ForegroundColor Cyan
            & $launcher schema apply
            if ($LASTEXITCODE -ne 0) { throw 'Schema apply failed' }
            $doctorText = & $launcher doctor | Out-String
            $doctor = $doctorText | ConvertFrom-Json
        } else {
            Write-Warning "连接成功，但表结构未就绪。先运行 schema plan，确认后再运行 schema apply。"
        }
    }
}

if (-not $SkipOpenBase) {
    Start-Process -FilePath $BaseUrl
}

[pscustomobject]@{
    configured = $true
    project = $resolvedProject
    identity_env = $identityPath
    project_env = Join-Path $localDir 'ledger.env'
    launcher = $launcher
    authorized = if ($doctor) { $doctor.authorized } else { $status.authorized }
    target_accessible = if ($doctor) { $doctor.target_accessible } else { $null }
    schema_ready = if ($doctor) { $doctor.schema_ready } else { $null }
    base_opened = -not $SkipOpenBase
}
