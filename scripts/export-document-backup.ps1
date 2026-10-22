#requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$ProjectId,
    [Parameter(Mandatory)][string]$Destination,
    [string]$BaseUrl = 'http://127.0.0.1:18081'
)

$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$target = (Resolve-Path -LiteralPath $Destination).Path.TrimEnd('\', '/')
if ($target -eq [IO.Path]::GetPathRoot($target).TrimEnd('\', '/') -or
    $target -eq $repo -or $repo.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $target.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destination must be a separate document directory outside OpenFic.'
}

function Test-Preserved([string]$Name) {
    return $Name -match '^(\.git|\.gitignore|\.gitattributes|archives|README(?:\.[^\\/]+)?|AGENTS(?:\.[^\\/]+)?)$'
}

function Assert-Clean {
    if (Test-Path -LiteralPath (Join-Path $target '.git')) {
        $status = & git -C $target status --porcelain --untracked-files=all
        if ($LASTEXITCODE -ne 0) { throw 'Cannot read destination Git status.' }
        if ($status) { throw 'Destination has uncommitted changes. Review them before exporting again.' }
    }
}

Assert-Clean
# Do not traverse links while replacing document files.
$links = Get-ChildItem -LiteralPath $target -Force -Recurse -Attributes ReparsePoint
if ($links) { throw 'Destination contains filesystem links; review them before exporting.' }
$run = Join-Path $repo ('output/exports/document-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
$stage = Join-Path $run 'export'
[IO.Directory]::CreateDirectory($stage) | Out-Null
$zip = Join-Path $run 'export.zip'
$escapedId = [Uri]::EscapeDataString($ProjectId)
Invoke-WebRequest -Uri ($BaseUrl.TrimEnd('/') + '/api/v1/projects/' + $escapedId + '/bundle/source/export') -OutFile $zip
$archive = [IO.Compression.ZipFile]::OpenRead($zip)
try {
    foreach ($entry in $archive.Entries) {
        $path = [IO.Path]::GetFullPath((Join-Path $stage $entry.FullName))
        if (-not $path.StartsWith($stage + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe archive path.' }
        $rootName = ($entry.FullName -split '[/\\]')[0]
        if (Test-Preserved $rootName) { throw "Export collides with preserved name: $rootName" }
    }
} finally { $archive.Dispose() }
[IO.Compression.ZipFile]::ExtractToDirectory($zip, $stage)
if (-not (Test-Path -LiteralPath (Join-Path $stage 'openfic-import.yaml') -PathType Leaf)) {
    throw 'Export is missing its mapping file.'
}
Assert-Clean
$before = Join-Path $run 'before'
[IO.Directory]::CreateDirectory($before) | Out-Null
$replace = @(Get-ChildItem -LiteralPath $target -Force | Where-Object { -not (Test-Preserved $_.Name) })
# Keep a recovery copy even for files not tracked by Git.
foreach ($item in $replace) { Copy-Item -LiteralPath $item.FullName -Destination $before -Recurse -Force }
@{ project_id = $ProjectId; destination = $target; source = $BaseUrl; exported_at = (Get-Date).ToString('o') } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $run 'export-info.json') -Encoding utf8
foreach ($item in $replace) {
    $resolved = [IO.Path]::GetFullPath($item.FullName)
    if ([IO.Path]::GetDirectoryName($resolved) -ne $target) { throw 'Deletion target is outside destination.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
foreach ($item in Get-ChildItem -LiteralPath $stage -Force) {
    Copy-Item -LiteralPath $item.FullName -Destination $target -Recurse -Force
}
foreach ($file in Get-ChildItem -LiteralPath $stage -File -Recurse) {
    $copy = Join-Path $target ([IO.Path]::GetRelativePath($stage, $file.FullName))
    if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $copy).Hash) {
        throw "Copy verification failed. Recovery files: $before"
    }
}
Write-Output "Exported project $ProjectId to $target"
Write-Output "Snapshot and recovery copy: $run"
if (Test-Path -LiteralPath (Join-Path $target '.git')) { & git -C $target diff --stat }
