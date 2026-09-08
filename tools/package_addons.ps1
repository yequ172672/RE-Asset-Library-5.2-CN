param(
    [Parameter(Mandatory = $true)]
    [string]$AssetSource,

    [Parameter(Mandatory = $true)]
    [string]$MeshSource,

    [Parameter(Mandatory = $true)]
    [string]$ChainSource,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$excludeDirectoryNames = @(
    ".git",
    ".pytest_cache",
    "__pycache__",
    "tests",
    "tools",
    "TextureCache",
    "TEMP",
    "_validation"
)

function Test-ExcludedRelativePath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $parts = $RelativePath -split "[\\/]"
    foreach ($part in $parts) {
        if ($excludeDirectoryNames -contains $part) {
            return $true
        }
        if ($part -eq "AGENTS.md") {
            return $true
        }
    }

    # Only exclude runtime updater directories. Source files such as
    # addon_updater_ops.py and re_mdf_updater_utils.py are required by the
    # installed add-on and must remain in the archive.
    for ($index = 0; $index -lt ($parts.Length - 1); $index += 1) {
        if ($parts[$index] -like "*_updater") {
            return $true
        }
    }

    if ($RelativePath -match "(?i)(\.py[cod]$|\.blend1$|\.log$)") {
        return $true
    }
    return $false
}

function New-AddonZip {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$InternalRoot,
        [Parameter(Mandatory = $true)][string]$ZipPath
    )

    $resolvedSource = (Resolve-Path -LiteralPath $Source).Path
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedSource "__init__.py") -PathType Leaf)) {
        throw "Add-on source has no __init__.py: $resolvedSource"
    }

    # The three package targets are explicit outputs of this tool. Replacing
    # an existing target is intentional and limited to the requested path.
    if ([System.IO.File]::Exists($ZipPath)) {
        [System.IO.File]::Delete($ZipPath)
    }
    $zip = [System.IO.Compression.ZipFile]::Open(
        $ZipPath,
        [System.IO.Compression.ZipArchiveMode]::Create
    )
    $fileCount = 0
    $byteCount = [int64]0
    try {
        $files = Get-ChildItem -LiteralPath $resolvedSource -Force -Recurse -File | Sort-Object FullName
        foreach ($file in $files) {
            $relative = [System.IO.Path]::GetRelativePath($resolvedSource, $file.FullName)
            if (Test-ExcludedRelativePath -RelativePath $relative) {
                continue
            }
            $entryName = ($InternalRoot + "/" + $relative.Replace("\", "/"))
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $zip,
                $file.FullName,
                $entryName,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
            $fileCount += 1
            $byteCount += $file.Length
        }
    }
    finally {
        $zip.Dispose()
    }

    [PSCustomObject]@{
        internalRoot = $InternalRoot
        source = $resolvedSource
        output = $ZipPath
        files = $fileCount
        sourceBytes = $byteCount
        zipBytes = (Get-Item -LiteralPath $ZipPath).Length
        sha256 = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null

$packages = @(
    New-AddonZip -Source $AssetSource -InternalRoot "RE-Asset-Library-main" -ZipPath (Join-Path $resolvedOutput "RE-Asset-Library-5.2-CN.zip")
    New-AddonZip -Source $MeshSource -InternalRoot "RE-Mesh-Editor-main" -ZipPath (Join-Path $resolvedOutput "RE-Mesh-Editor-5.2-CN.zip")
    New-AddonZip -Source $ChainSource -InternalRoot "RE-Chain-Editor-main" -ZipPath (Join-Path $resolvedOutput "RE-Chain-Editor-5.2-CN.zip")
)

$manifest = [PSCustomObject]@{
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    excluded = $excludeDirectoryNames + @("*_updater/", "AGENTS.md", "*.py[cod]", "*.blend1", "*.log")
    packages = $packages
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $resolvedOutput "package_manifest.json") -Encoding UTF8
$packages | Format-Table -AutoSize
