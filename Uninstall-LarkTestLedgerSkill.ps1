[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [switch]$KeepIdentity
)

$ErrorActionPreference = 'Stop'
$userProfile = [Environment]::GetFolderPath('UserProfile')
$codexRoot = if ($env:CODEX_HOME) { [IO.Path]::GetFullPath($env:CODEX_HOME) } else { Join-Path $userProfile '.codex' }
$skill = Join-Path $codexRoot 'skills\lark-test-ledger'
$compatibility = Join-Path $userProfile '.agents\skills\lark-test-ledger'
$identity = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'LarkTestLedger'

if ($PSCmdlet.ShouldProcess($skill, 'Remove global Lark test ledger Skill')) {
    if (Test-Path -LiteralPath $compatibility) { Remove-Item -LiteralPath $compatibility }
    if (Test-Path -LiteralPath $skill) { Remove-Item -LiteralPath $skill -Recurse }
    if (-not $KeepIdentity -and (Test-Path -LiteralPath $identity)) {
        Remove-Item -LiteralPath $identity -Recurse
    }
}
