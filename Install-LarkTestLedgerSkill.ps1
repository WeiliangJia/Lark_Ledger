#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$SourceSkill = (Join-Path $PSScriptRoot 'skill\lark-test-ledger'),
    [string]$IdentityEnv,
    [switch]$SkipCompatibilityLink,
    [ValidateSet('Codex', 'ClaudeCode', 'Qoder')]
    [string]$Client = 'Codex'
)

$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $SourceSkill).Path
$userProfile = [Environment]::GetFolderPath('UserProfile')
$codexRoot = if ($env:CODEX_HOME) { [IO.Path]::GetFullPath($env:CODEX_HOME) } else { Join-Path $userProfile '.codex' }
$skillsRoot = switch ($Client) {
    'Codex' { Join-Path $codexRoot 'skills' }
    'ClaudeCode' { Join-Path $userProfile '.claude\skills' }
    'Qoder' { Join-Path $userProfile '.qoder\skills' }
}
$target = Join-Path $skillsRoot 'lark-test-ledger'
if (Test-Path -LiteralPath $target) {
    throw "Skill 已存在：$target。请先备份并显式更新，安装器不会覆盖已有文件。"
}
New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Recurse

$compatibility = $null
if ($Client -eq 'Codex' -and -not $SkipCompatibilityLink) {
    $agentsSkills = Join-Path $userProfile '.agents\skills'
    New-Item -ItemType Directory -Force -Path $agentsSkills | Out-Null
    $compatibility = Join-Path $agentsSkills 'lark-test-ledger'
    if (-not (Test-Path -LiteralPath $compatibility)) {
        New-Item -ItemType Junction -Path $compatibility -Target $target | Out-Null
    }
}

if ($IdentityEnv) {
    $identity = (Resolve-Path -LiteralPath $IdentityEnv).Path
    & (Join-Path $target 'scripts\Setup-LarkTestLedgerIdentity.ps1') -ReuseIdentityEnv $identity -SkipAuth | Out-Host
}

[pscustomobject]@{
    installed = $true
    client = $Client
    skill = $target
    compatibility_link = $compatibility
    identity_configured = [bool]$IdentityEnv
    chat_invocation = '@Lark 测试账本'
    codex_invocation = '$lark-test-ledger'
    restart_if_not_visible = $true
}
