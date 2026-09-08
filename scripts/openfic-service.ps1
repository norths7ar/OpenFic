#Requires -Version 7.4
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'logs', 'backup', 'restore')]
    [string]$Action = 'status',
    [string]$DataPath,
    [int]$Port = 18081,
    [string]$SnapshotPath,
    [string]$BrowserBackupPath,
    [string]$RestorePath,
    [string]$RestoreEnvironmentPath
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$backendRoot = Join-Path $projectRoot 'backend'
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$dataDirectory = if ($DataPath) { [IO.Path]::GetFullPath($DataPath) } else { Join-Path $projectRoot 'data' }
$runtimeDirectory = Join-Path $dataDirectory 'runtime'
$logDirectory = Join-Path $dataDirectory 'logs'
$statePath = Join-Path $runtimeDirectory 'openfic.json'
$frontendDirectory = Join-Path $projectRoot 'frontend\dist'
$healthUri = "http://127.0.0.1:$port/api/v1/health"
$pathSettingNames = @('COVERS_DIR', 'CHARACTER_IMAGES_DIR', 'AGENT_ATTACHMENTS_DIR', 'CHAPTER_EXPORTS_DIR', 'STATIC_DIR', 'AGENT_CHECKPOINT_DB')
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

function ConvertTo-ManagedPathSettings {
    param($Values)
    $paths = [ordered]@{}
    foreach ($name in $pathSettingNames) {
        $value = if ($Values -is [Collections.IDictionary]) { $Values[$name] } else { $Values.$name }
        if ([string]::IsNullOrWhiteSpace([string]$value) -or -not [IO.Path]::IsPathFullyQualified([string]$value)) {
            throw "Managed path setting is missing or not absolute: $name"
        }
        $paths[$name] = [IO.Path]::GetFullPath([string]$value)
    }
    return $paths
}

function Get-ConfiguredPathSettings {
    Push-Location -LiteralPath $backendRoot
    try {
        $output = & $pythonPath -m app.backup paths --data $dataDirectory --repository $projectRoot
        if ($LASTEXITCODE -ne 0) { throw 'Unable to resolve the managed data paths.' }
        return ConvertTo-ManagedPathSettings ($output | ConvertFrom-Json -AsHashtable)
    }
    finally { Pop-Location }
}

function Test-PathIsWithin {
    param([string]$Path, [string]$Root)
    $relative = [IO.Path]::GetRelativePath($Root, $Path)
    return -not ([IO.Path]::IsPathRooted($relative) -or $relative -eq '..' -or $relative.StartsWith("..$([IO.Path]::DirectorySeparatorChar)"))
}

function Get-RestorePathSettings {
    $environmentPath = [IO.Path]::GetFullPath($RestoreEnvironmentPath)
    $restoreRoot = [IO.Path]::GetFullPath((Split-Path -Parent $environmentPath))
    if ([IO.Path]::GetFileName($environmentPath) -ne 'restore-environment.json') {
        throw 'Restore environment must be the generated restore-environment.json file.'
    }
    $restoreEnvironment = Get-Content -LiteralPath $environmentPath -Raw | ConvertFrom-Json -AsHashtable
    $expectedDataDirectory = Join-Path $restoreRoot 'data'
    if (-not $restoreEnvironment.ContainsKey('OPENFIC_DATA_DIR') -or
        [IO.Path]::GetFullPath([string]$restoreEnvironment.OPENFIC_DATA_DIR) -ne $expectedDataDirectory -or
        $dataDirectory -ne $expectedDataDirectory) {
        throw 'Restored environment does not match the restored data directory.'
    }
    foreach ($entry in $restoreEnvironment.GetEnumerator()) {
        if ($entry.Key -notin @('OPENFIC_DATA_DIR') + $pathSettingNames) {
            throw "Unsupported restore environment setting: $($entry.Key)"
        }
        $value = [IO.Path]::GetFullPath([string]$entry.Value)
        if (-not (Test-PathIsWithin $value $restoreRoot)) {
            throw "Restored environment points outside the restore directory: $($entry.Key)"
        }
        if ((Test-Path -LiteralPath $value) -and
            (([IO.File]::GetAttributes($value) -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Restored environment path cannot be a link: $($entry.Key)"
        }
    }
    return ConvertTo-ManagedPathSettings $restoreEnvironment
}

function Start-OpenFic {
    param([System.Collections.IDictionary]$ManagedPaths)
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
    if (-not [string]::IsNullOrWhiteSpace($env:ENCRYPTION_KEY)) {
        throw "Process ENCRYPTION_KEY is not supported by the managed service. Store it in $dataDirectory\.env instead."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendDirectory 'index.html'))) {
        throw 'Run pnpm build in frontend before starting OpenFic.'
    }
    $effectivePaths = if ($RestoreEnvironmentPath) {
        Get-RestorePathSettings
    } elseif ($null -ne $ManagedPaths) {
        ConvertTo-ManagedPathSettings $ManagedPaths
    } else {
        Get-ConfiguredPathSettings
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
    foreach ($entry in $effectivePaths.GetEnumerator()) {
        $parameters.Environment[$entry.Key] = [string]$entry.Value
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
                paths = $effectivePaths
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

function Invoke-SnapshotCommand {
    param([string[]]$SnapshotArguments)
    Push-Location -LiteralPath $backendRoot
    try {
        & $pythonPath -m app.backup @SnapshotArguments
        if ($LASTEXITCODE -ne 0) { throw 'Snapshot operation failed; formal data was not replaced.' }
    }
    finally { Pop-Location }
}

if ($Action -eq 'restore') {
    if (-not $SnapshotPath -or -not $RestorePath) { throw 'restore requires -SnapshotPath and -RestorePath (a new directory).' }
    Invoke-SnapshotCommand @('restore', '--snapshot', [IO.Path]::GetFullPath($SnapshotPath), '--destination', [IO.Path]::GetFullPath($RestorePath))
    $restoredRoot = [IO.Path]::GetFullPath($RestorePath)
    $sourceScript = Join-Path $restoredRoot 'source\scripts\openfic-service.ps1'
    Write-Output "Restored to $restoredRoot. To run the matching source, first run 'uv sync --frozen' in $restoredRoot\source\backend, then use:"
    Write-Output "& '$sourceScript' start -DataPath '$restoredRoot\data' -RestoreEnvironmentPath '$restoredRoot\restore-environment.json' -Port 18082"
    return
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
        'restart' {
            $restartState = Read-ServiceState
            $restartPaths = if ($null -ne $restartState -and $null -ne $restartState.paths) {
                ConvertTo-ManagedPathSettings $restartState.paths
            } else { $null }
            Stop-OpenFic
            Start-OpenFic -ManagedPaths $restartPaths
        }
        'backup' {
            if (-not $SnapshotPath) {
                $SnapshotPath = Join-Path $projectRoot ("output/backups/" + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
            }
            $snapshotArguments = @('create', '--data', $dataDirectory, '--repository', $projectRoot, '--snapshot', [IO.Path]::GetFullPath($SnapshotPath))
            if ($BrowserBackupPath) { $snapshotArguments += @('--browser', [IO.Path]::GetFullPath($BrowserBackupPath)) }
            $backupState = Read-ServiceState
            $wasRunning = $null -ne (Get-OwnedProcess $backupState)
            $backupPaths = if ($null -ne $backupState -and $null -ne $backupState.paths) {
                ConvertTo-ManagedPathSettings $backupState.paths
            } else { Get-ConfiguredPathSettings }
            $pathsFile = New-TemporaryFile
            $backupPaths | ConvertTo-Json | Set-Content -LiteralPath $pathsFile -Encoding utf8
            $snapshotArguments += @('--paths-file', $pathsFile.FullName)
            Stop-OpenFic
            try { Invoke-SnapshotCommand $snapshotArguments }
            finally {
                Remove-Item -LiteralPath $pathsFile -Force -ErrorAction SilentlyContinue
                if ($wasRunning) { Start-OpenFic -ManagedPaths $backupPaths }
            }
            Write-Output "Snapshot: $SnapshotPath"
            if (-not $BrowserBackupPath) { Write-Output 'Server snapshot only: export the browser companion separately to include unsubmitted work.' }
        }
    }
}
finally { $lock.Dispose() }
