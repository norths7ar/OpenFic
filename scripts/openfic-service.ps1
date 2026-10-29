#Requires -Version 7.4
<#
.SYNOPSIS
Manage the local OpenFic instance independently of Service Desk.
.DESCRIPTION
status always writes one JSON object (schema_version 1): state, detail, pid (null
when no owned process is verified), port, data_directory, and optionally busy.
running, stopped and known abnormal warning states exit 0; inspection errors are
unknown and exit 1. A held management lock is warning with busy=true, not stopped.
Status only reads existing files and never creates the data/runtime directories.

start/stop/restart retain human output by default. -Json instead writes one status
object plus ok and action. Success exits 0 only after healthy startup or confirmed
shutdown; failure exits 1 with a readable stderr message (and ok=false with -Json).
Existing runtime state/lock formats are unchanged. Service Desk integrates through
this script's public command interface, not its runtime files.
backup and restore retain human output; -Json is only for lifecycle and status.
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'backup', 'restore')]
    [string]$Action = 'status',
    [string]$DataPath,
    [int]$Port = 18081,
    [string]$SnapshotPath,
    [string]$BrowserBackupPath,
    [string]$RestorePath,
    [string]$RestoreEnvironmentPath,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$Action = $Action.ToLowerInvariant()
$dataDirectory = $null
$operationStage = 'initialization'
$privateValues = [Collections.Generic.List[string]]::new()
foreach ($value in @($env:OPENFIC_SHUTDOWN_TOKEN, $env:ENCRYPTION_KEY)) {
    if (-not [string]::IsNullOrEmpty($value)) { $privateValues.Add($value) }
}

function Initialize-Manager {
    $script:projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
    $script:backendRoot = Join-Path $projectRoot 'backend'
    $script:pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
    $script:dataDirectory = if ($DataPath) { [IO.Path]::GetFullPath($DataPath) } else { Join-Path $projectRoot 'data' }
    if ($Port -lt 1 -or $Port -gt 65535) { Throw-ManagerError 'Port must be between 1 and 65535.' }
    $script:runtimeDirectory = Join-Path $dataDirectory 'runtime'
    $script:logDirectory = Join-Path $dataDirectory 'logs'
    $script:statePath = Join-Path $runtimeDirectory 'openfic.json'
    $script:lockPath = Join-Path $runtimeDirectory 'openfic.lock'
    # The existing runtime state/lock format is unchanged; SD calls this script.
    $script:frontendDirectory = Join-Path $projectRoot 'frontend\dist'
    $script:healthUri = "http://127.0.0.1:$port/api/v1/health"
    $script:pathSettingNames = @('COVERS_DIR', 'CHARACTER_IMAGES_DIR', 'AGENT_ATTACHMENTS_DIR', 'CHAPTER_EXPORTS_DIR', 'STATIC_DIR', 'AGENT_CHECKPOINT_DB')
    $script:basePython = ''
    $venvConfig = Join-Path $backendRoot '.venv\pyvenv.cfg'
    if (Test-Path -LiteralPath $venvConfig) {
        foreach ($line in Get-Content -LiteralPath $venvConfig) {
            if ($line -match '^home\s*=\s*(.+)$') {
                $script:basePython = [IO.Path]::GetFullPath((Join-Path $Matches[1].Trim() 'python.exe'))
                break
            }
        }
    }
}

function Throw-ManagerError {
    param([string]$Detail, [string]$State = 'unknown', [switch]$Busy)
    $failure = [InvalidOperationException]::new($Detail)
    $failure.Data['OpenFicDetail'] = $Detail
    $failure.Data['OpenFicState'] = $State
    $failure.Data['OpenFicBusy'] = $Busy.IsPresent
    throw $failure
}

function Get-ManagerFailure {
    param([Exception]$Exception)
    # JSON parse errors and HTTP response bodies are replaced at their source;
    # other failures retain their cause, with known credentials redacted.
    $cause = $Exception
    while ($null -ne $cause) {
        if ($cause.Data.Contains('OpenFicDetail')) {
            return New-ManagerStatus $cause.Data['OpenFicState'] (Protect-ManagerDetail $cause.Data['OpenFicDetail']) -Busy:([bool]$cause.Data['OpenFicBusy'])
        }
        if ($cause -is [UnauthorizedAccessException]) {
            return New-ManagerStatus 'unknown' "Access denied during $operationStage. Check filesystem and process inspection permissions."
        }
        $cause = $cause.InnerException
    }
    $detail = Protect-ManagerDetail $Exception.GetBaseException().Message
    return New-ManagerStatus 'unknown' "OpenFic $Action failed during ${operationStage}: $detail"
}

function Protect-ManagerDetail {
    param([string]$Detail)
    foreach ($value in $privateValues) { $Detail = $Detail.Replace($value, '[redacted]') }
    return $Detail
}

function Get-NativeFailureDetail {
    param([string]$Context, [int]$ExitCode, $Output)
    # Keep the final error reason, not an entire traceback or configuration dump.
    $lastLine = $Output | ForEach-Object { ([string]$_) -split '\r?\n' } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1
    $detail = "$Context (exit $ExitCode)"
    if ($lastLine) { $detail += ': ' + (Protect-ManagerDetail $lastLine) }
    return $detail
}

function New-ManagerStatus {
    param([string]$State, [string]$Detail, [Nullable[int]]$ProcessId = $null, [switch]$Busy)
    $result = [ordered]@{
        schema_version = 1
        state = $State
        detail = $Detail
        pid = $ProcessId
        port = $Port
        data_directory = $dataDirectory
    }
    if ($Busy) { $result.busy = $true }
    return $result
}

function Test-ManagerBusy {
    $probe = $null
    try {
        # Open, not OpenOrCreate: status must not create any runtime artifacts.
        $probe = [IO.File]::Open($lockPath, 'Open', 'Read', 'ReadWrite')
        return $false
    }
    catch [IO.FileNotFoundException] { return $false }
    catch [IO.DirectoryNotFoundException] { return $false }
    catch [IO.IOException] {
        # Only Windows sharing/lock violations mean busy. Access denied and
        # all other inspection failures must remain unknown/nonzero.
        if (($_.Exception.HResult -band 0xffff) -in @(32, 33)) { return $true }
        throw
    }
    finally { if ($null -ne $probe) { $probe.Dispose() } }
}

function Get-ListeningProcessIds {
    $script:operationStage = 'listening-port inspection'
    $lines = & (Join-Path $env:SystemRoot 'System32\netstat.exe') @('-ano', '-p', 'tcp')
    if ($LASTEXITCODE -ne 0) { Throw-ManagerError 'Unable to inspect listening ports.' }
    $ids = foreach ($line in $lines) {
        if ($line -match '^\s*TCP\s+\S+:([0-9]+)\s+\S+\s+LISTENING\s+([0-9]+)\s*$' -and
            [int]$Matches[1] -eq $port) { [int]$Matches[2] }
    }
    return @($ids | Sort-Object -Unique)
}

function Read-ServiceState {
    $script:operationStage = 'runtime-state inspection'
    try { $content = [IO.File]::ReadAllText($statePath, [Text.Encoding]::UTF8) }
    catch [IO.FileNotFoundException] { return $null }
    catch [IO.DirectoryNotFoundException] { return $null }
    try {
        $state = ConvertFrom-Json -InputObject $content
        $recordedId = 0
        $recordedPort = 0
        $recordedStart = [datetime]::MinValue
        if ($state -isnot [pscustomobject] -or
            -not [int]::TryParse([string]$state.pid, [ref]$recordedId) -or $recordedId -le 0 -or
            -not [int]::TryParse([string]$state.port, [ref]$recordedPort) -or
            -not [datetime]::TryParse([string]$state.started_at, [ref]$recordedStart) -or
            [string]::IsNullOrWhiteSpace([string]$state.python) -or
            [string]::IsNullOrWhiteSpace([string]$state.data_directory)) {
            throw 'Invalid runtime state structure.'
        }
        if (-not [string]::IsNullOrEmpty([string]$state.shutdown_token)) {
            $privateValues.Add([string]$state.shutdown_token)
        }
        return $state
    }
    catch { Throw-ManagerError "Invalid OpenFic state file: $statePath. Existing state was preserved." }
}

function Get-OwnedProcess {
    param($State)
    if ($null -eq $State) { return $null }
    $script:operationStage = 'process identity inspection'
    try { $process = [Diagnostics.Process]::GetProcessById([int]$State.pid) }
    catch [ArgumentException] { return $null }
    $info = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
    if ($null -eq $info) {
        if ($process.HasExited) { return $null }
        Throw-ManagerError 'Unable to inspect the recorded OpenFic process. Existing state was preserved.'
    }
    if ([string]::IsNullOrWhiteSpace($info.ExecutablePath) -or [string]::IsNullOrWhiteSpace($info.CommandLine)) {
        Throw-ManagerError 'OpenFic process identity is not visible. Run the manager with full process visibility; existing state was preserved.'
    }
    if ($State.python -ne $pythonPath -or $State.data_directory -ne $dataDirectory -or
        [int]$State.port -ne $port -or
        $process.StartTime.ToUniversalTime() -ne ([datetime]$State.started_at).ToUniversalTime() -or
        ($info.ExecutablePath -ne $pythonPath -and $info.ExecutablePath -ne $basePython) -or
        $info.CommandLine -notmatch '-m\s+app\.cli\s+serve\s' -or
        $info.CommandLine -notmatch "--port\s+$port(?:\s|$)") {
        Throw-ManagerError 'Recorded PID does not identify this OpenFic service. Refusing to manage it.' -State 'warning'
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
            Throw-ManagerError "Managed path setting is missing or not absolute: $name"
        }
        $paths[$name] = [IO.Path]::GetFullPath([string]$value)
    }
    return $paths
}

function Get-ConfiguredPathSettings {
    $script:operationStage = 'managed-path resolution'
    Push-Location -LiteralPath $backendRoot
    try {
        $output = & $pythonPath -m app.backup paths --data $dataDirectory --repository $projectRoot 2>&1
        $commandExitCode = $LASTEXITCODE
        if ($commandExitCode -ne 0) { Throw-ManagerError (Get-NativeFailureDetail 'Unable to resolve the managed data paths' $commandExitCode $output) }
        try { $values = ($output -join "`n") | ConvertFrom-Json -AsHashtable }
        catch { Throw-ManagerError 'Managed path resolution did not return valid JSON.' }
        return ConvertTo-ManagedPathSettings $values
    }
    finally { Pop-Location }
}

function Test-PathIsWithin {
    param([string]$Path, [string]$Root)
    $relative = [IO.Path]::GetRelativePath($Root, $Path)
    return -not ([IO.Path]::IsPathRooted($relative) -or $relative -eq '..' -or $relative.StartsWith("..$([IO.Path]::DirectorySeparatorChar)"))
}

function Get-RestorePathSettings {
    $script:operationStage = 'restore-environment validation'
    $environmentPath = [IO.Path]::GetFullPath($RestoreEnvironmentPath)
    $restoreRoot = [IO.Path]::GetFullPath((Split-Path -Parent $environmentPath))
    if ([IO.Path]::GetFileName($environmentPath) -ne 'restore-environment.json') {
        Throw-ManagerError 'Restore environment must be the generated restore-environment.json file.'
    }
    $content = Get-Content -LiteralPath $environmentPath -Raw
    try { $restoreEnvironment = ConvertFrom-Json -InputObject $content -AsHashtable }
    catch { Throw-ManagerError 'Restore environment is not valid JSON.' }
    $expectedDataDirectory = Join-Path $restoreRoot 'data'
    if (-not $restoreEnvironment.ContainsKey('OPENFIC_DATA_DIR') -or
        [IO.Path]::GetFullPath([string]$restoreEnvironment.OPENFIC_DATA_DIR) -ne $expectedDataDirectory -or
        $dataDirectory -ne $expectedDataDirectory) {
        Throw-ManagerError 'Restored environment does not match the restored data directory.'
    }
    foreach ($entry in $restoreEnvironment.GetEnumerator()) {
        if ($entry.Key -notin @('OPENFIC_DATA_DIR') + $pathSettingNames) {
            Throw-ManagerError 'Restore environment contains an unsupported setting.'
        }
        $value = [IO.Path]::GetFullPath([string]$entry.Value)
        if (-not (Test-PathIsWithin $value $restoreRoot)) {
            Throw-ManagerError "Restored environment points outside the restore directory: $($entry.Key)"
        }
        if ((Test-Path -LiteralPath $value) -and
            (([IO.File]::GetAttributes($value) -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            Throw-ManagerError "Restored environment path cannot be a link: $($entry.Key)"
        }
    }
    return ConvertTo-ManagedPathSettings $restoreEnvironment
}

function Start-DetachedOpenFicProcess {
    param([string]$StdoutPath, [string]$StderrPath, [Collections.IDictionary]$Environment)
    # Start-Process can leave an external caller's capture pipes inherited by
    # descendants. Python restricts inheritance to these explicit log handles,
    # gives the service null stdin and detaches it from the manager's console.
    $launchCode = @'
import subprocess
import sys

with open(sys.argv[1], "ab", buffering=0) as stdout, open(sys.argv[2], "ab", buffering=0) as stderr:
    process = subprocess.Popen(
        sys.argv[3:],
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    print(process.pid, flush=True)
'@
    $startInfo = [Diagnostics.ProcessStartInfo]::new($pythonPath)
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WorkingDirectory = $backendRoot
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in @('-c', $launchCode, $StdoutPath, $StderrPath, $pythonPath, '-m', 'app.cli', 'serve', '--host', '127.0.0.1', '--port', [string]$port)) {
        $startInfo.ArgumentList.Add($argument)
    }
    foreach ($entry in $Environment.GetEnumerator()) { $startInfo.Environment[$entry.Key] = [string]$entry.Value }
    $bootstrap = [Diagnostics.Process]::Start($startInfo)
    try {
        $bootstrap.StandardInput.Close()
        $stdoutTask = $bootstrap.StandardOutput.ReadToEndAsync()
        $stderrTask = $bootstrap.StandardError.ReadToEndAsync()
        if (-not $bootstrap.WaitForExit(15000)) {
            $bootstrap.Kill($true)
            $null = $bootstrap.WaitForExit(5000)
            Throw-ManagerError 'The detached OpenFic launcher did not finish within 15 seconds.'
        }
        $launchOutput = $stdoutTask.GetAwaiter().GetResult()
        $launchError = $stderrTask.GetAwaiter().GetResult()
        if ($bootstrap.ExitCode -ne 0) {
            Throw-ManagerError (Get-NativeFailureDetail 'Unable to launch detached OpenFic' $bootstrap.ExitCode $launchError)
        }
        $launcherId = 0
        if (-not [int]::TryParse($launchOutput.Trim(), [ref]$launcherId) -or $launcherId -le 0) {
            Throw-ManagerError 'The detached OpenFic launcher did not return a valid process ID.'
        }
        try { return [Diagnostics.Process]::GetProcessById($launcherId) }
        catch [ArgumentException] { Throw-ManagerError "OpenFic exited during detached launch. See $StderrPath" }
    }
    finally { $bootstrap.Dispose() }
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
        Throw-ManagerError 'The managed OpenFic process is alive but not healthy. Check logs or stop it first.' -State 'warning'
    }
    if ($listeners.Count -gt 0) { Throw-ManagerError "Port $port is occupied by unmanaged PID(s): $($listeners -join ', ')." -State 'warning' }
    if (Test-Health) { Throw-ManagerError 'OpenFic is reachable but its process ownership cannot be verified. Run the manager with full process visibility; existing state was preserved.' -State 'warning' }
    if (-not (Test-Path -LiteralPath $pythonPath)) { Throw-ManagerError "Run uv sync --frozen in backend first: $pythonPath" }
    if (-not [string]::IsNullOrWhiteSpace($env:ENCRYPTION_KEY)) {
        Throw-ManagerError "Process ENCRYPTION_KEY is not supported by the managed service. Store it in $dataDirectory\.env instead."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendDirectory 'index.html'))) {
        Throw-ManagerError 'Run pnpm build in frontend before starting OpenFic.'
    }
    # A restart/backup must restore the paths of the running instance, even if
    # the invoking environment or restore-environment file has since changed.
    $effectivePaths = if ($null -ne $ManagedPaths) {
        ConvertTo-ManagedPathSettings $ManagedPaths
    } elseif ($RestoreEnvironmentPath) {
        Get-RestorePathSettings
    } else {
        Get-ConfiguredPathSettings
    }
    $script:operationStage = 'service startup'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $stdout = Join-Path $logDirectory "openfic-$stamp.stdout.log"
    $stderr = Join-Path $logDirectory "openfic-$stamp.stderr.log"
    $shutdownToken = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    $privateValues.Add($shutdownToken)
    $serviceEnvironment = @{
        OPENFIC_DATA_DIR = $dataDirectory
        OPENFIC_FRONTEND_DIST = $frontendDirectory
        OPENFIC_SHUTDOWN_TOKEN = $shutdownToken
        PYTHONUNBUFFERED = '1'
    }
    foreach ($entry in $effectivePaths.GetEnumerator()) {
        $serviceEnvironment[$entry.Key] = [string]$entry.Value
    }
    $launcher = Start-DetachedOpenFicProcess -StdoutPath $stdout -StderrPath $stderr -Environment $serviceEnvironment
    $startupComplete = $false
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(45)
        while ([DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Milliseconds 250
            $launcher.Refresh()
            if ($launcher.HasExited) { Throw-ManagerError "OpenFic exited during startup. See $stderr" }
            $listeners = Get-ListeningProcessIds
            if ($listeners.Count -ne 1 -or -not (Test-Health)) { continue }
            $listenerId = [int]$listeners[0]
            $info = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerId"
            if ($listenerId -ne $launcher.Id -and $info.ParentProcessId -ne $launcher.Id) {
                Throw-ManagerError 'Port was claimed by a different process during startup.' -State 'warning'
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
            $null = Get-OwnedProcess $state
            $script:operationStage = 'runtime-state publication'
            $temporaryState = Join-Path $runtimeDirectory ("openfic-" + [Guid]::NewGuid().ToString('N') + '.tmp')
            try {
                $state | ConvertTo-Json | Set-Content -LiteralPath $temporaryState -Encoding utf8
                [IO.File]::Move($temporaryState, $statePath, $true)
            }
            finally {
                if (Test-Path -LiteralPath $temporaryState) { Remove-Item -LiteralPath $temporaryState }
            }
            $startupComplete = $true
            Write-Output "OpenFic started in background. PID: $listenerId. http://127.0.0.1:$port/"
            return
        }
        Throw-ManagerError "OpenFic did not become healthy within 45 seconds. See $stderr"
    }
    finally {
        if (-not $startupComplete) {
            $launcher.Refresh()
            if (-not $launcher.HasExited) { $launcher.Kill($true); $null = $launcher.WaitForExit(5000) }
        }
    }
}

function Stop-OpenFic {
    param([Collections.IDictionary]$ShutdownProgress = @{})
    $ShutdownProgress.request_state = 'not_sent'
    $state = Read-ServiceState
    $process = Get-OwnedProcess $state
    $ShutdownProgress.process = $process
    if ($null -eq $process) {
        if (Test-Health) {
            Throw-ManagerError 'OpenFic is reachable but its process ownership cannot be verified. Run the manager with full process visibility; existing state was preserved.' -State 'warning'
        }
        if ((Get-ListeningProcessIds).Count -gt 0) {
            Throw-ManagerError "Port $port has an unmanaged listener; refusing to stop it." -State 'warning'
        }
        # Do not erase credentials merely because this process cannot see the
        # recorded PID. A successful start can atomically replace stale state.
        Write-Output 'OpenFic is not running.'
        return
    }
    if ($process.Id -notin (Get-ListeningProcessIds)) {
        Throw-ManagerError 'Managed process is not listening; inspect logs before stopping it manually.' -State 'warning'
    }
    $script:operationStage = 'authenticated graceful shutdown'
    if ([string]::IsNullOrWhiteSpace([string]$state.shutdown_token)) {
        Throw-ManagerError 'The managed state has no shutdown credential. Existing state was preserved.'
    }
    # Retain the original process handle before sending shutdown, so recovery
    # waits for this process rather than a potentially reused PID.
    $null = $process.Handle
    $ShutdownProgress.request_state = 'uncertain'
    try {
        $null = Invoke-RestMethod -Uri "$healthUri/shutdown" -Method Post -TimeoutSec 5 -Headers @{
            'X-OpenFic-Shutdown-Token' = [string]$state.shutdown_token
        }
        $ShutdownProgress.request_state = 'accepted'
    }
    catch {
        # A lost response may still mean shutdown was accepted. Only definite
        # request/authentication rejections allow leaving a healthy process alone.
        if ($_.Exception -is [Microsoft.PowerShell.Commands.HttpResponseException] -and
            [int]$_.Exception.Response.StatusCode -in @(400, 401, 403, 404, 405, 422)) {
            $ShutdownProgress.request_state = 'rejected'
        }
        Throw-ManagerError 'OpenFic graceful shutdown request failed. Check authentication, connectivity and service logs; existing state was preserved.'
    }
    if (-not $process.WaitForExit(30000)) {
        Throw-ManagerError "OpenFic has not finished shutting down. PID: $($process.Id). No forced termination was performed." -State 'warning'
    }
    if ((Get-ListeningProcessIds).Count -gt 0 -or (Test-Health)) {
        Throw-ManagerError 'The managed process exited, but the service port is still reachable. Existing state was preserved.' -State 'warning'
    }
    $script:operationStage = 'runtime-state removal'
    Remove-Item -LiteralPath $statePath
    Write-Output "OpenFic stopped gracefully. PID: $($process.Id)."
}

function Get-OpenFicStatus {
    param([switch]$LockHeld)
    $script:operationStage = 'management-lock inspection'
    if (-not $LockHeld -and (Test-ManagerBusy)) {
        return New-ManagerStatus 'warning' 'Another lifecycle or backup operation holds the OpenFic management lock.' -Busy
    }
    $state = Read-ServiceState
    try { $process = Get-OwnedProcess $state }
    catch {
        $failure = Get-ManagerFailure $_.Exception
        if ($failure.state -ne 'warning') { throw }
        return $failure
    }
    $listeners = Get-ListeningProcessIds
    if ($null -ne $process -and $process.Id -in $listeners -and (Test-Health)) {
        return New-ManagerStatus 'running' 'Process identity, listening port and health check passed.' -ProcessId $process.Id
    }
    if ($null -ne $process) {
        return New-ManagerStatus 'warning' 'The managed process is alive but its listening port or health check failed.' -ProcessId $process.Id
    }
    if ($listeners.Count -gt 0 -or (Test-Health)) {
        return New-ManagerStatus 'warning' 'The service port is reachable without a verified owned process. Existing state was preserved.'
    }
    return New-ManagerStatus 'stopped' 'No managed process, listening port or healthy endpoint was found.'
}

function Invoke-SnapshotCommand {
    param([string[]]$SnapshotArguments)
    $script:operationStage = "snapshot $($SnapshotArguments[0])"
    Push-Location -LiteralPath $backendRoot
    try {
        # Capture diagnostics so the caller receives a concise, redacted reason.
        $output = & $pythonPath -m app.backup @SnapshotArguments 2>&1
        $commandExitCode = $LASTEXITCODE
        if ($commandExitCode -ne 0) { Throw-ManagerError ((Get-NativeFailureDetail 'Snapshot operation failed' $commandExitCode $output) + '; formal data was not replaced.') }
        Write-Output "Snapshot $($SnapshotArguments[0]) completed."
    }
    finally { Pop-Location }
}

function Restore-OpenFicSnapshot {
    if (-not $SnapshotPath -or -not $RestorePath) { Throw-ManagerError 'restore requires -SnapshotPath and -RestorePath (a new directory).' }
    Invoke-SnapshotCommand @('restore', '--snapshot', [IO.Path]::GetFullPath($SnapshotPath), '--destination', [IO.Path]::GetFullPath($RestorePath))
    $restoredRoot = [IO.Path]::GetFullPath($RestorePath)
    $sourceScript = Join-Path $restoredRoot 'source\scripts\openfic-service.ps1'
    Write-Output "Restored to $restoredRoot. First restore dependencies (including the default deployment group):"
    Write-Output "uv sync --frozen --project '$restoredRoot\source\backend'"
    Write-Output "& '$sourceScript' start -DataPath '$restoredRoot\data' -RestoreEnvironmentPath '$restoredRoot\restore-environment.json' -Port 18082"
}

function Backup-OpenFicSnapshot {
    if (-not $SnapshotPath) {
        $SnapshotPath = Join-Path $projectRoot ("output/backups/" + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    }
    $snapshotArguments = @('create', '--data', $dataDirectory, '--repository', $projectRoot, '--snapshot', [IO.Path]::GetFullPath($SnapshotPath))
    if ($BrowserBackupPath) { $snapshotArguments += @('--browser', [IO.Path]::GetFullPath($BrowserBackupPath)) }
    $backupState = Read-ServiceState
    $backupProcess = Get-OwnedProcess $backupState
    $wasRunning = $null -ne $backupProcess
    $backupPaths = if ($null -ne $backupState -and $null -ne $backupState.paths) {
        ConvertTo-ManagedPathSettings $backupState.paths
    } else { Get-ConfiguredPathSettings }
    $pathsFile = $null
    $stopAttempted = $false
    $stopCompleted = $false
    $shutdownProgress = @{ process = $backupProcess; request_state = 'not_sent' }
    $failures = [Collections.Generic.List[string]]::new()
    try {
        $script:operationStage = 'backup path staging'
        $temporaryDirectory = Join-Path $projectRoot '.tmp'
        New-Item -ItemType Directory -Path $temporaryDirectory -Force | Out-Null
        $pathsFile = Join-Path $temporaryDirectory ((Get-Date -Format 'yyyyMMdd') + '-openfic-backup-paths-' + [Guid]::NewGuid().ToString('N') + '.json')
        $backupPaths | ConvertTo-Json | Set-Content -LiteralPath $pathsFile -Encoding utf8
        $snapshotArguments += @('--paths-file', $pathsFile)
        $stopAttempted = $true
        Stop-OpenFic -ShutdownProgress $shutdownProgress
        $stopCompleted = $true
        Invoke-SnapshotCommand $snapshotArguments
    }
    catch { $failures.Add((Get-ManagerFailure $_.Exception).detail) }
    finally {
        # Recovery must run even if snapshot creation, shutdown, or temporary
        # file cleanup fails. Start uses the original, captured path settings.
        if ($wasRunning -and $stopAttempted) {
            try {
                $restartRequired = $true
                if (-not $stopCompleted) {
                    $script:operationStage = 'backup shutdown recovery'
                    $originalProcess = if ($null -ne $shutdownProgress.process) { $shutdownProgress.process } else { $backupProcess }
                    if (-not $originalProcess.HasExited) {
                        if ($shutdownProgress.request_state -in @('accepted', 'uncertain')) {
                            if (-not $originalProcess.WaitForExit(30000)) {
                                Throw-ManagerError 'Recovery could not confirm the original process exited within 30 additional seconds after an accepted or uncertain shutdown request. No restart or forced termination was performed.' -State 'warning'
                            }
                        } else {
                            $remainingProcess = Get-OwnedProcess $backupState
                            if ($null -eq $remainingProcess -or $remainingProcess.Id -notin (Get-ListeningProcessIds) -or -not (Test-Health)) {
                                Throw-ManagerError 'Recovery could not confirm the original process is healthy after shutdown was not accepted. No restart or forced termination was performed.' -State 'warning'
                            }
                            $restartRequired = $false
                            Write-Output 'Shutdown was not accepted; the original OpenFic process remains healthy. No recovery restart was performed.'
                        }
                    }
                }
                if ($restartRequired) { Start-OpenFic -ManagedPaths $backupPaths }
            }
            catch { $failures.Add("Recovery after backup failed: $((Get-ManagerFailure $_.Exception).detail)") }
        }
        if ($null -ne $pathsFile) {
            $script:operationStage = 'backup temporary-file cleanup'
            try { Remove-Item -LiteralPath $pathsFile -Force }
            catch { $failures.Add((Get-ManagerFailure $_.Exception).detail) }
        }
    }
    if ($failures.Count -gt 0) { Throw-ManagerError ($failures -join ' ') }
    Write-Output "Snapshot: $SnapshotPath"
    if (-not $BrowserBackupPath) { Write-Output 'Server snapshot only: export the browser companion separately to include unsubmitted work.' }
}

function Invoke-ManagerAction {
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
        'backup' { Backup-OpenFicSnapshot }
    }
}

$lock = $null
try {
    Initialize-Manager
    if ($Json -and $Action -in @('backup', 'restore')) {
        Throw-ManagerError '-Json is supported only for start, stop, restart and status.'
    }
    if ($Action -eq 'status') {
        $result = Get-OpenFicStatus
        $result | ConvertTo-Json -Compress
        exit 0
    }
    # Restore creates a separate copy; it does not operate on the live instance.
    if ($Action -eq 'restore') { Restore-OpenFicSnapshot; exit 0 }
    $script:operationStage = 'management-lock acquisition'
    New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
    try { $lock = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None') }
    catch [IO.IOException] {
        if (($_.Exception.HResult -band 0xffff) -in @(32, 33)) {
            Throw-ManagerError 'Another lifecycle or backup operation holds the OpenFic management lock. No lifecycle action was performed.' -State 'warning' -Busy
        }
        throw
    }
    if ($Json) { $null = Invoke-ManagerAction }
    else { Invoke-ManagerAction }
    if ($Action -in @('start', 'stop', 'restart')) {
        $result = Get-OpenFicStatus -LockHeld
        $expectedState = if ($Action -eq 'stop') { 'stopped' } else { 'running' }
        if ($result.state -ne $expectedState) {
            Throw-ManagerError "OpenFic $Action could not be confirmed: $($result.detail)" -State $result.state
        }
        if ($Json) {
            $result.ok = $true
            $result.action = $Action
            $result | ConvertTo-Json -Compress
        }
    }
    exit 0
}
catch {
    $result = Get-ManagerFailure $_.Exception
    if ($Action -eq 'status') { $result | ConvertTo-Json -Compress }
    else {
        [Console]::Error.WriteLine($result.detail)
        if ($Json) {
            $result.ok = $false
            $result.action = $Action
            $result | ConvertTo-Json -Compress
        }
    }
    exit 1
}
finally { if ($null -ne $lock) { $lock.Dispose() } }
