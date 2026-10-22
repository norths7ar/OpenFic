#Requires -Version 7.4
[CmdletBinding()]
param(
    [string[]]$Extra = @(),
    [string]$DataPath,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'
$syncArguments = @((Join-Path $PSScriptRoot 'sync-dependencies.py'))
foreach ($name in $Extra) { $syncArguments += @('--extra', $name) }
if ($DataPath) { $syncArguments += @('--data-path', [IO.Path]::GetFullPath($DataPath)) }
if ($DryRun) { $syncArguments += '--dry-run' }

if (Test-Path -LiteralPath $pythonPath) {
    & $pythonPath @syncArguments
} else {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    $uvPath = if ($uvCommand) { $uvCommand.Source } else { Join-Path $HOME '.local/bin/uv.exe' }
    # Bootstrap without syncing the project before its extras have been recorded.
    & $uvPath run --no-project --python 3.13 @syncArguments
}
if ($LASTEXITCODE -ne 0) { throw "Dependency synchronization failed (exit $LASTEXITCODE)." }
