[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$SharedIdentityEnv,

    [string]$TableName = '测试用例',
    [string]$Python = 'python',
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolvedIdentity = (Resolve-Path -LiteralPath $SharedIdentityEnv).Path
$candidateRoot = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'src\dms_test_ledger')) {
    $PSScriptRoot
} else {
    Join-Path $PSScriptRoot '..'
}
$frameworkRoot = (Resolve-Path -LiteralPath $candidateRoot).Path
$localDir = Join-Path $resolvedProject '.lark-test-ledger'
$envFile = Join-Path $localDir 'ledger.env'
$venvDir = Join-Path $localDir '.venv'
$launcher = Join-Path $localDir 'lark-ledger.ps1'
$frameworkCopy = Join-Path $localDir 'framework\src\dms_test_ledger'

New-Item -ItemType Directory -Force -Path $localDir | Out-Null

$identityForEnv = $resolvedIdentity
$envLines = @(
    "LARK_IDENTITY_ENV_FILE=$identityForEnv",
    '',
    "LARK_BASE_URL=$BaseUrl",
    "LARK_TABLE_NAME=$TableName",
    '',
    'LEDGER_STATE_DB=state.sqlite3',
    'LEDGER_ARCHIVE_DIR=manifests'
)
Set-Content -LiteralPath $envFile -Value $envLines -Encoding utf8NoBOM

if (-not $SkipInstall) {
    & $Python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed' }
    $runtimePython = Join-Path $venvDir 'Scripts\python.exe'
} else {
    $runtimePython = (Get-Command $Python -ErrorAction Stop).Source
}

# This package has no third-party runtime dependencies. Copy only source files
# instead of invoking pip, so bootstrapping works without network or wheel.
New-Item -ItemType Directory -Force -Path $frameworkCopy | Out-Null
$sourcePackage = Join-Path $frameworkRoot 'src\dms_test_ledger'
Get-ChildItem -LiteralPath $sourcePackage -File -Filter '*.py' |
    Copy-Item -Destination $frameworkCopy -Force

$runtimePythonForScript = $runtimePython.Replace("'", "''")
$frameworkSourceForScript = (Join-Path $localDir 'framework\src').Replace("'", "''")

$launcherLines = @(
    '$ErrorActionPreference = ''Stop''',
    '$localDir = $PSScriptRoot',
    "`$python = '$runtimePythonForScript'",
    "`$frameworkSource = '$frameworkSourceForScript'",
    'if (-not (Test-Path -LiteralPath $python)) { throw ''Configured Python runtime is missing; rerun Initialize-LarkTestProject.ps1'' }',
    '$env:PYTHONPATH = $frameworkSource + [IO.Path]::PathSeparator + $env:PYTHONPATH',
    '$env:PYTHONUTF8 = ''1''',
    '$envFile = Join-Path $localDir ''ledger.env''',
    '& $python -m dms_test_ledger --env-file $envFile @args',
    'exit $LASTEXITCODE'
)
Set-Content -LiteralPath $launcher -Value $launcherLines -Encoding utf8NoBOM

$gitIgnore = Join-Path $resolvedProject '.gitignore'
$ignoreEntry = '.lark-test-ledger/'
$existingIgnore = if (Test-Path -LiteralPath $gitIgnore) { Get-Content -LiteralPath $gitIgnore } else { @() }
if ($existingIgnore -notcontains $ignoreEntry) {
    Add-Content -LiteralPath $gitIgnore -Value $ignoreEntry -Encoding utf8NoBOM
}

[pscustomobject]@{
    project = $resolvedProject
    env_file = $envFile
    launcher = $launcher
    identity_referenced = $resolvedIdentity
    secret_copied = $false
    isolated_venv = -not $SkipInstall
    framework_source = $frameworkCopy
}
