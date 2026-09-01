[CmdletBinding()]
param(
    [string]$ReuseIdentityEnv,
    [string]$IdentityEnv,
    [string]$AppId,
    [string]$AppSecret,
    [string]$RedirectUri = 'http://127.0.0.1:8765/callback',
    [switch]$SkipAuth
)

$ErrorActionPreference = 'Stop'
$configRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'LarkTestLedger'
New-Item -ItemType Directory -Force -Path $configRoot | Out-Null
$pointerFile = Join-Path $configRoot 'skill.env'

if ($ReuseIdentityEnv) {
    $resolvedIdentity = (Resolve-Path -LiteralPath $ReuseIdentityEnv).Path
} else {
    if (-not $IdentityEnv) { $IdentityEnv = Join-Path $configRoot 'identity.env' }
    $resolvedIdentity = [IO.Path]::GetFullPath($IdentityEnv)
    if (-not (Test-Path -LiteralPath $resolvedIdentity)) {
        if (-not $AppId) { $AppId = Read-Host '请输入公司自建 Lark App ID' }
        if (-not $AppSecret) {
            $secureSecret = Read-Host '请输入公司自建 Lark App Secret（输入会隐藏）' -AsSecureString
            $AppSecret = [Net.NetworkCredential]::new('', $secureSecret).Password
        }
        if (-not $AppId.Trim() -or -not $AppSecret) { throw 'App ID and App Secret must not be empty' }
        $identityDir = Split-Path -Parent $resolvedIdentity
        New-Item -ItemType Directory -Force -Path $identityDir | Out-Null
        $identityLines = @(
            "LARK_APP_ID=$($AppId.Trim())",
            "LARK_APP_SECRET=$AppSecret",
            "LARK_REDIRECT_URI=$RedirectUri",
            'LARK_OAUTH_SCOPES=offline_access bitable:app wiki:node:read auth:user.id:read',
            '',
            "LEDGER_STATE_DB=$(Join-Path $identityDir 'identity-state.sqlite3')",
            "LARK_TOKEN_DB=$(Join-Path $identityDir 'oauth.sqlite3')",
            "LARK_OAUTH_LOCK_PATH=$(Join-Path $identityDir 'oauth-refresh.lock')",
            "LEDGER_ARCHIVE_DIR=$(Join-Path $identityDir 'manifests')",
            'LARK_BATCH_SIZE=200',
            'LARK_REQUEST_TIMEOUT=30'
        )
        Set-Content -LiteralPath $resolvedIdentity -Value $identityLines -Encoding utf8NoBOM
        $AppSecret = $null
        $secureSecret = $null
    } else {
        $resolvedIdentity = (Resolve-Path -LiteralPath $resolvedIdentity).Path
    }
}

Set-Content -LiteralPath $pointerFile -Value "LARK_IDENTITY_ENV_FILE=$resolvedIdentity" -Encoding utf8NoBOM

if (-not $SkipAuth) {
    $runtime = Join-Path $PSScriptRoot 'lark-test-ledger.pyz'
    $pythonCommand = Get-Command python -ErrorAction Stop
    $env:PYTHONUTF8 = '1'
    $statusText = & $pythonCommand.Source $runtime --env-file $resolvedIdentity status | Out-String
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read Lark identity status' }
    $status = $statusText | ConvertFrom-Json
    if (-not $status.authorized) {
        Write-Host '即将打开 Lark 授权页面。请本人完成登录、MFA 和授权。' -ForegroundColor Cyan
        & $pythonCommand.Source $runtime --env-file $resolvedIdentity auth
        if ($LASTEXITCODE -ne 0) { throw 'Lark authorization failed' }
    }
}

[pscustomobject]@{
    configured = $true
    identity_env = $resolvedIdentity
    pointer_file = $pointerFile
    secret_copied_to_skill = $false
}
