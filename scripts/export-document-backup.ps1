#requires -Version 7.0
[CmdletBinding(DefaultParameterSetName = 'Configured')]
param(
    [Parameter(ParameterSetName = 'Configured')][string]$Book,
    [Parameter(ParameterSetName = 'Configured')][string]$ConfigPath = (Join-Path $PSScriptRoot 'document-backups.json'),
    [Parameter(Mandatory, ParameterSetName = 'Explicit')][string]$ProjectId,
    [Parameter(Mandatory, ParameterSetName = 'Explicit')][string]$Destination,
    [string]$BaseUrl = 'http://127.0.0.1:18081'
)

$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
function Test-Preserved([string]$Name) {
    return $Name -match '^(\.git|\.gitignore|\.gitattributes|archives|README(?:\.[^\\/]+)?|AGENTS(?:\.[^\\/]+)?)$'
}

function Assert-Clean([string]$target) {
    if (Test-Path -LiteralPath (Join-Path $target '.git')) {
        $status = & git -C $target status --porcelain --untracked-files=all
        if ($LASTEXITCODE -ne 0) { throw 'Cannot read destination Git status.' }
        if ($status) { throw "目标仓库有未提交修改，请先处理：$target" }
    }
}

function Resolve-Target([string]$Destination) {
    $target = (Resolve-Path -LiteralPath $Destination).Path.TrimEnd('\', '/')
    if ($target -eq [IO.Path]::GetPathRoot($target).TrimEnd('\', '/') -or
        $target -eq $repo -or $repo.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $target.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Destination must be a separate document directory outside OpenFic.'
    }

    $item = Get-Item -LiteralPath $target
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "目标必须是普通目录：$target"
    }
    Assert-Clean $target
    $links = Get-ChildItem -LiteralPath $target -Force -Recurse -Attributes ReparsePoint
    if ($links) { throw "目标包含文件系统链接：$target" }
    return $target
}

if ($PSCmdlet.ParameterSetName -eq 'Explicit') {
    $books = @([pscustomobject]@{ name = $ProjectId; project_id = $ProjectId; destination = $Destination })
} else {
    $configFile = (Resolve-Path -LiteralPath $ConfigPath).Path
    $books = @(Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json)
    if (-not $books.Count) { throw '备份配置为空。' }
    foreach ($entry in $books) {
        if (-not $entry.name -or -not $entry.project_id -or -not $entry.destination) {
            throw '每本书必须配置 name、project_id 和 destination。'
        }
        $entry.destination = [IO.Path]::GetFullPath($entry.destination, (Split-Path $configFile))
    }
    if ($Book) {
        $available = ($books.name -join '、')
        $books = @($books | Where-Object { $_.name -eq $Book })
        if ($books.Count -ne 1) { throw "书名不存在或不唯一：$Book。可选：$available" }
    }
}
# Check every selected destination before downloading or replacing any book.
$seen = @{}
foreach ($entry in $books) {
    $entry.destination = Resolve-Target $entry.destination
    foreach ($other in $seen.Keys) {
        if ($entry.destination -eq $other -or $entry.destination.StartsWith($other + '\', [StringComparison]::OrdinalIgnoreCase) -or $other.StartsWith($entry.destination + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "备份目录重复或互相包含：$($entry.destination) / $other"
        }
    }
    $seen[$entry.destination] = $true
}

function Get-Snapshot([string]$Root) {
    $result = @{}
    foreach ($item in Get-ChildItem -LiteralPath $Root -Force) {
        if (Test-Preserved $item.Name) { continue }
        $files = if ($item.PSIsContainer) { Get-ChildItem -LiteralPath $item.FullName -File -Recurse -Force } else { $item }
        foreach ($file in $files) {
            $result[[IO.Path]::GetRelativePath($Root, $file.FullName)] = (Get-FileHash -LiteralPath $file.FullName).Hash
        }
    }
    return $result
}

function Export-Book($entry) {
    $ProjectId = $entry.project_id
    $target = $entry.destination
    # Do not traverse links while replacing document files.
    $links = Get-ChildItem -LiteralPath $target -Force -Recurse -Attributes ReparsePoint
    if ($links) { throw 'Destination contains filesystem links; review them before exporting.' }
    $run = Join-Path $repo ('output/exports/document-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    $stage = Join-Path $run 'export'
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    $zip = Join-Path $run 'export.zip'
    $escapedId = [Uri]::EscapeDataString($ProjectId)
    Invoke-WebRequest -Uri ($BaseUrl.TrimEnd('/') + '/api/v1/projects/' + $escapedId + '/bundle/source/export') -OutFile $zip
    $archive = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        foreach ($archiveEntry in $archive.Entries) {
            $path = [IO.Path]::GetFullPath((Join-Path $stage $archiveEntry.FullName))
            if (-not $path.StartsWith($stage + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe archive path.' }
            $rootName = ($archiveEntry.FullName -split '[/\\]')[0]
            if (Test-Preserved $rootName) { throw "Export collides with preserved name: $rootName" }
        }
    } finally { $archive.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, $stage)
    if (-not (Test-Path -LiteralPath (Join-Path $stage 'openfic-import.yaml') -PathType Leaf)) {
        throw 'Export is missing its mapping file.'
    }
    $null = Resolve-Target $target
    $old = Get-Snapshot $target
    $new = Get-Snapshot $stage
    $added = @($new.Keys | Where-Object { -not $old.ContainsKey($_) }).Count
    $deleted = @($old.Keys | Where-Object { -not $new.ContainsKey($_) }).Count
    $modified = @($new.Keys | Where-Object { $old.ContainsKey($_) -and $old[$_] -ne $new[$_] }).Count
    if (-not ($added + $deleted + $modified)) {
        Write-Output "$($entry.name)：没有变化。导出快照：$run"
        return
    }
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
    Write-Output "$($entry.name)：新增 $added，修改 $modified，删除 $deleted。"
    Write-Output "备份目录：$target"
    Write-Output "导出快照和替换前副本：$run"
}

foreach ($entry in $books) {
    try { Export-Book $entry }
    catch { throw "《$($entry.name)》备份失败：$($_.Exception.Message)；此前已完成的备份保留。" }
}
