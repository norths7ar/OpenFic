#Requires -Version 7.4
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'logs')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$backendRoot = Join-Path $projectRoot 'backend'
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$dataDirectory = Join-Path $projectRoot 'data'
$runtimeDirectory = Join-Path $dataDirectory 'runtime'
$logDirectory = Join-Path $dataDirectory 'logs'
$statePath = Join-Path $runtimeDirectory 'openfic.json'
$frontendDirectory = Join-Path $projectRoot 'frontend\dist'
$port = 18081
$healthUri = "http://127.0.0.1:$port/api/v1/health"
$basePython = ''
$venvConfig = Join-Path $backendRoot '.venv\pyvenv.cfg'
if (Test-Path -LiteralPath $venvConfig) {
    foreach ($line in Get-Content -LiteralPath $venvConfig) {
        if ($line -match '^home\s*=\s*(.+)$') {
            $basePython = [IO.Path]::GetFullPath((Join-Path $Matches[1].Trim() 'python.exe'))
            break
        }
    }
}

function Get-ListeningProcessIds {
    $lines = & (Join-Path $env:SystemRoot 'System32\netstat.exe') @('-ano', '-p', 'tcp')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect listening ports.' }
    $ids = foreach ($line in $lines) {
        if ($line -match '^\s*TCP\s+\S+:([0-9]+)\s+\S+\s+LISTENING\s+([0-9]+)\s*$' -and
            [int]$Matches[1] -eq $port) { [int]$Matches[2] }
    }
    return @($ids | Sort-Object -Unique)
}

function Read-ServiceState {
    if (-not (Test-Path -LiteralPath $statePath)) { return $null }
    try { return Get-Content -LiteralPath $statePath -Raw -Encoding utf8 | ConvertFrom-Json }
    catch { throw "Invalid OpenFic state file: $statePath" }
}

function Get-OwnedProcess {
    param($State)
    if ($null -eq $State) { return $null }
    $process = Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    $info = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
    if ($State.python -ne $pythonPath -or $State.data_directory -ne $dataDirectory -or
        [int]$State.port -ne $port -or
        $process.StartTime.ToUniversalTime() -ne ([datetime]$State.started_at).ToUniversalTime() -or
        $null -eq $info -or
        ($info.ExecutablePath -ne $pythonPath -and $info.ExecutablePath -ne $basePython) -or
        $info.CommandLine -notmatch '-m\s+app\.cli\s+serve\s' -or
        $info.CommandLine -notmatch "--port\s+$port(?:\s|$)") {
        throw 'Recorded PID does not identify this OpenFic service. Refusing to manage it.'
    }
    return $process
}

function Test-Health {
    try { return (Invoke-RestMethod -Uri $healthUri -TimeoutSec 2).status -eq 'healthy' }
    catch { return $false }
}

function Start-OpenFic {
    $state = Read-ServiceState
    $existing = Get-OwnedProcess $state
    $listeners = Get-ListeningProcessIds
    if ($null -ne $existing) {
        if ($existing.Id -in $listeners -and (Test-Health)) {
            Write-Output "OpenFic is already running. PID: $($existing.Id). http://127.0.0.1:$port/"
            return
        }
        throw 'The managed OpenFic process is alive but not healthy. Check logs or stop it first.'
    }
    if ($listeners.Count -gt 0) { throw "Port $port is occupied by unmanaged PID(s): $($listeners -join ', ')." }
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw "Run uv sync --frozen in backend first: $pythonPath" }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendDirectory 'index.html'))) {
        throw 'Run pnpm build in frontend before starting OpenFic.'
    }
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $stdout = Join-Path $logDirectory "openfic-$stamp.stdout.log"
    $stderr = Join-Path $logDirectory "openfic-$stamp.stderr.log"
    $shutdownToken = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    $parameters = @{
        FilePath = $pythonPath
        ArgumentList = @('-m', 'app.cli', 'serve', '--host', '127.0.0.1', '--port', [string]$port)
        WorkingDirectory = $backendRoot
        WindowStyle = 'Hidden'
        RedirectStandardOutput = $stdout
        RedirectStandardError = $stderr
        PassThru = $true
        Environment = @{
            OPENFIC_DATA_DIR = $dataDirectory
            OPENFIC_FRONTEND_DIST = $frontendDirectory
            OPENFIC_SHUTDOWN_TOKEN = $shutdownToken
            PYTHONUNBUFFERED = '1'
        }
    }
    $launcher = Start-Process @parameters
    $startupComplete = $false
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(45)
        while ([DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Milliseconds 250
            $launcher.Refresh()
            if ($launcher.HasExited) { throw "OpenFic exited during startup. See $stderr" }
            $listeners = Get-ListeningProcessIds
            if ($listeners.Count -ne 1 -or -not (Test-Health)) { continue }
            $listenerId = [int]$listeners[0]
            $info = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerId"
            if ($listenerId -ne $launcher.Id -and $info.ParentProcessId -ne $launcher.Id) {
                throw 'Port was claimed by a different process during startup.'
            }
            $listener = Get-Process -Id $listenerId -ErrorAction Stop
            $state = [ordered]@{
                pid = $listenerId
                launcher_pid = $launcher.Id
                started_at = $listener.StartTime.ToUniversalTime().ToString('o')
                python = $pythonPath
                data_directory = $dataDirectory
                port = $port
                stdout = $stdout
                stderr = $stderr
                shutdown_token = $shutdownToken
            }
            $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
            $startupComplete = $true
            Write-Output "OpenFic started in background. PID: $listenerId. http://127.0.0.1:$port/"
            return
        }
        throw "OpenFic did not become healthy within 45 seconds. See $stderr"
    }
    finally {
        if (-not $startupComplete) {
            $launcher.Refresh()
            if (-not $launcher.HasExited) { $launcher.Kill($true); $null = $launcher.WaitForExit(5000) }
        }
    }
}

function Stop-OpenFic {
    $state = Read-ServiceState
    $process = Get-OwnedProcess $state
    if ($null -eq $process) {
        if ((Get-ListeningProcessIds).Count -gt 0) {
            throw "Port $port has an unmanaged listener; refusing to stop it."
        }
        if (Test-Path -LiteralPath $statePath) { Remove-Item -LiteralPath $statePath }
        Write-Output 'OpenFic is not running.'
        return
    }
    if ($process.Id -notin (Get-ListeningProcessIds)) {
        throw 'Managed process is not listening; inspect logs before stopping it manually.'
    }
    $null = Invoke-RestMethod -Uri "$healthUri/shutdown" -Method Post -TimeoutSec 5 -Headers @{
        'X-OpenFic-Shutdown-Token' = [string]$state.shutdown_token
    }
    if (-not $process.WaitForExit(30000)) {
        throw "OpenFic has not finished shutting down. PID: $($process.Id). No forced termination was performed."
    }
    Remove-Item -LiteralPath $statePath
    Write-Output "OpenFic stopped gracefully. PID: $($process.Id)."
}

function Show-OpenFicStatus {
    $state = Read-ServiceState
    $process = Get-OwnedProcess $state
    $listeners = Get-ListeningProcessIds
    if ($null -ne $process -and $process.Id -in $listeners -and (Test-Health)) {
        Write-Output "OpenFic is running. PID: $($process.Id). http://127.0.0.1:$port/"
        return
    }
    if ($null -ne $process -or $listeners.Count -gt 0) { throw 'OpenFic process/port status is abnormal. Inspect logs.' }
    Write-Output 'OpenFic is not running.'
    exit 1
}

function Show-OpenFicLogs {
    $state = Read-ServiceState
    if ($null -ne $state) { $paths = @($state.stdout, $state.stderr) }
    else {
        $latest = Get-ChildItem -LiteralPath $logDirectory -Filter 'openfic-*.stdout.log' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($null -eq $latest) { Write-Output 'No OpenFic service logs yet.'; return }
        $paths = @($latest.FullName, ($latest.FullName -replace '\.stdout\.log$', '.stderr.log'))
    }
    foreach ($path in $paths) {
        if (Test-Path -LiteralPath $path) {
            Write-Output $path
            Get-Content -LiteralPath $path -Tail 60 -Encoding utf8
        }
    }
}

if ($Action -eq 'status') { Show-OpenFicStatus; return }
if ($Action -eq 'logs') { Show-OpenFicLogs; return }
New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
# Serialize start/stop so two invocations cannot open the same data directory twice.
$lock = [IO.File]::Open((Join-Path $runtimeDirectory 'openfic.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
    switch ($Action) {
        'start' { Start-OpenFic }
        'stop' { Stop-OpenFic }
        'restart' { Stop-OpenFic; Start-OpenFic }
    }
}
finally { $lock.Dispose() }
