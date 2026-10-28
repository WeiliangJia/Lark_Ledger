#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Get-Location).Path,
    [ValidateSet('Codex', 'ClaudeCode', 'Qoder')]
    [string]$Client,
    [string]$BaseUrl,
    [string]$TableName = '测试用例',
    [string]$IdentityEnv,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
try {
    if (-not $IsWindows) { throw '当前安装向导支持 Windows 10/11。请在 Windows 的 PowerShell 7 中运行。' }
    Write-Host '[1/5] 检查运行环境' -ForegroundColor Cyan
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw '未找到 Python。请安装 Python 3.11+ 并勾选加入 PATH，重新打开终端后再运行。下载：https://www.python.org/downloads/' }
    try { & $python.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' }
    catch { throw 'Python 无法启动，可能命中了 Windows 应用执行别名。请安装 Python 3.11+，加入 PATH，并在系统设置中关闭无效的 python.exe 应用执行别名。' }
    if ($LASTEXITCODE -ne 0) { throw 'Python 无法运行或版本低于 3.11。请升级 Python，并检查终端中的 python --version。' }
    $project = (Resolve-Path -LiteralPath $ProjectRoot).Path
    if (-not (Test-Path -LiteralPath $project -PathType Container)) { throw 'ProjectRoot 必须是已存在的项目文件夹。' }
    if ($CheckOnly) { Write-Host '环境检查通过：Windows、PowerShell 7、Python 3.11+，项目目录存在。'; return }
    $existingConfig = Join-Path $project '.lark-test-ledger\ledger.env'
    if ((Test-Path -LiteralPath $existingConfig) -and $BaseUrl) { throw '项目已配置，未应用新的 BaseUrl。请核实并手动更新 ledger.env 后重新运行。' }
    if ($BaseUrl -and $BaseUrl -notmatch '^https://.+/(base|wiki)/[^?]+\?.*\btable=[A-Za-z0-9_-]+') { throw 'Base 地址无效。请复制包含 table=<table_id> 的 https Base/Wiki 完整地址。' }

    Write-Host '[2/5] 选择客户端并安装 Skill' -ForegroundColor Cyan
    if (-not $Client) {
        $choice = Read-Host '选择客户端：1 Codex（默认） / 2 Claude Code / 3 Qoder'
        $Client = switch ($choice.Trim()) { '' { 'Codex' }; '1' { 'Codex' }; '2' { 'ClaudeCode' }; '3' { 'Qoder' }; default { throw '请选择 1、2 或 3，重新运行即可。' } }
    }
    $userProfile = [Environment]::GetFolderPath('UserProfile')
    $skillRoot = switch ($Client) {
        'Codex' {
            $codexRoot = if ($env:CODEX_HOME) { [IO.Path]::GetFullPath($env:CODEX_HOME) } else { Join-Path $userProfile '.codex' }
            Join-Path $codexRoot 'skills\lark-test-ledger'
        }
        'ClaudeCode' { Join-Path $userProfile '.claude\skills\lark-test-ledger' }
        'Qoder' { Join-Path $userProfile '.qoder\skills\lark-test-ledger' }
    }
    if (-not (Test-Path -LiteralPath $skillRoot)) {
        & (Join-Path $PSScriptRoot 'Install-LarkTestLedgerSkill.ps1') -Client $Client | Out-Host
    } else {
        Write-Host "保留已有 Skill：$skillRoot"
    }
    foreach ($file in @('SKILL.md', 'scripts\Invoke-LarkTestLedger.ps1', 'scripts\lark-test-ledger.pyz')) {
        if (-not (Test-Path -LiteralPath (Join-Path $skillRoot $file))) { throw "已有 Skill 不完整，缺少 $file。请备份后重新安装。" }
    }

    Write-Host '[3/5] 配置本机身份（不会输出凭据）' -ForegroundColor Cyan
    $identityArgs = @{ SkipAuth = $true }
    if ($IdentityEnv) { $identityArgs.ReuseIdentityEnv = $IdentityEnv }
    else {
        $pointer = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'LarkTestLedger\skill.env'
        if (Test-Path -LiteralPath $pointer) {
            $line = Get-Content -LiteralPath $pointer | Where-Object { $_ -match '^LARK_IDENTITY_ENV_FILE=' } | Select-Object -First 1
            if (-not $line) { throw "身份指针无效：$pointer。请用 -IdentityEnv 指定有效的身份文件。" }
            $identityArgs.ReuseIdentityEnv = ($line -split '=', 2)[1].Trim()
        }
    }
    $identity = & (Join-Path $skillRoot 'scripts\Setup-LarkTestLedgerIdentity.ps1') @identityArgs

    Write-Host '[4/5] 配置项目并引导 Lark 授权' -ForegroundColor Cyan
    $projectConfig = Join-Path $project '.lark-test-ledger\ledger.env'
    if (Test-Path -LiteralPath $projectConfig) {
        Write-Host '保留现有项目配置；不会替换目标 Base。'
        $invoke = Join-Path $skillRoot 'scripts\Invoke-LarkTestLedger.ps1'
        $statusText = & $invoke -ProjectRoot $project status | Out-String
        if ($LASTEXITCODE -ne 0) { throw '无法读取项目授权状态。请按上方提示修复配置后重试。' }
        if (-not ($statusText | ConvertFrom-Json).authorized) {
            & $invoke -ProjectRoot $project auth | Out-Host
            if ($LASTEXITCODE -ne 0) { throw '授权未完成。请确认回调地址为 http://127.0.0.1:8765/callback，重新运行后在浏览器完成授权。' }
        }
    } else {
        if (-not $BaseUrl) { $BaseUrl = Read-Host '请输入目标 Base/Wiki 完整地址（包含 table=...）' }
        & (Join-Path $skillRoot 'scripts\Setup-LarkTestLedgerProject.ps1') -ProjectRoot $project -BaseUrl $BaseUrl -TableName $TableName -IdentityEnv $identity.identity_env -SkipDoctor | Out-Host
    }

    Write-Host '[5/5] 检查 Base 访问权限和字段（只读）' -ForegroundColor Cyan
    $doctorText = & (Join-Path $skillRoot 'scripts\Invoke-LarkTestLedger.ps1') -ProjectRoot $project doctor | Out-String
    if ($LASTEXITCODE -ne 0) { throw '连接检查失败。请按上方中文提示处理后重新运行；已有配置会保留。' }
    $doctor = $doctorText | ConvertFrom-Json
    if (-not $doctor.ready) { throw 'Base 可访问，但字段不完整或类型冲突。请先运行 doctor / schema plan 查看差异；确认目标和权限后再决定是否执行 schema apply。' }
    Write-Host "初始化完成。请重新打开 $Client，使用 lark-test-ledger Skill。" -ForegroundColor Green
    Write-Host "项目目录：$project；Skill：$skillRoot"
} catch {
    Write-Error "初始化未完成：$($_.Exception.Message)" -ErrorAction Continue
    exit 1
}
