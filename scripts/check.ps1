[CmdletBinding()]
param(
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [switch]$SkipTests,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $repositoryRoot 'backend'
$frontendPath = Join-Path $repositoryRoot 'frontend'

function Invoke-QualityCommand {
    param(
        [Parameter(Mandatory)]
        [string]$Command,

        [string[]]$Arguments = @()
    )

    & $Command @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Command failed with exit code $exitCode."
    }
}

if (-not $SkipBackend) {
    Push-Location -LiteralPath $backendPath
    try {
        Invoke-QualityCommand -Command 'uv' -Arguments @('run', 'ruff', 'format', '--check', '.')
        Invoke-QualityCommand -Command 'uv' -Arguments @('run', 'ruff', 'check', '.')
        Invoke-QualityCommand -Command 'uv' -Arguments @('run', 'ty', 'check', 'app')

        if (-not $SkipTests) {
            Invoke-QualityCommand -Command 'uv' -Arguments @('run', 'pytest')
        }
    }
    finally {
        Pop-Location
    }
}

if (-not $SkipFrontend) {
    Push-Location -LiteralPath $frontendPath
    try {
        Invoke-QualityCommand -Command 'pnpm' -Arguments @('run', 'format:check')
        Invoke-QualityCommand -Command 'pnpm' -Arguments @('run', 'lint')
        Invoke-QualityCommand -Command 'pnpm' -Arguments @('run', 'type-check')
        if (-not $SkipTests) {
            Invoke-QualityCommand -Command 'pnpm' -Arguments @('run', 'test')
        }

        if (-not $SkipBuild) {
            Invoke-QualityCommand -Command 'pnpm' -Arguments @('run', 'build')
        }
    }
    finally {
        Pop-Location
    }
}
