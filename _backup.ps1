# TestPilot AI - Backup Script
# Creates a zip backup excluding junk dirs, named by date+time

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackupDir = "D:\Projects\Backups"
$Timestamp = Get-Date -Format "MMddHHmm"
$ZipName = "TestPilot_AI_$Timestamp.zip"
$ZipPath = Join-Path $BackupDir $ZipName

# Ensure backup dir exists
if (-not (Test-Path $BackupDir)) { New-Item -Path $BackupDir -ItemType Directory -Force | Out-Null }

# Dirs and files to exclude
$ExcludeDirs = @('.venv', '__pycache__', '.mypy_cache', '.pytest_cache',
                 'node_modules', 'data', 'logs', '.git', '.windsurf',
                 'target', 'dist', 'out')
$ExcludeExts = @('.pyc', '.pyo', '.log', '.vhdx', '.exe', '.msi')

Write-Host ""
Write-Host "========================================"
Write-Host "  TestPilot AI Backup"
Write-Host "========================================"
Write-Host "  Project : $ProjectDir"
Write-Host "  Output  : $ZipPath"
Write-Host ""

# Create temp staging dir
$TempDir = Join-Path $env:TEMP "TP_bak_$Timestamp"
if (Test-Path $TempDir) { Remove-Item $TempDir -Recurse -Force }
New-Item -Path $TempDir -ItemType Directory -Force | Out-Null

Write-Host "[1/3] Copying project files..."

# Copy files, filtering out excluded dirs and extensions
Get-ChildItem -Path $ProjectDir -Recurse -Force -ErrorAction SilentlyContinue | Where-Object {
    $rel = $_.FullName.Substring($ProjectDir.Length).TrimStart('\')
    $parts = $rel.Split('\')
    # Skip if any path segment is an excluded dir
    $skip = $false
    foreach ($p in $parts) {
        if ($ExcludeDirs -contains $p) { $skip = $true; break }
    }
    if (-not $skip -and -not $_.PSIsContainer) {
        # Skip excluded extensions
        if ($ExcludeExts -contains $_.Extension) { $skip = $true }
    }
    -not $skip
} | ForEach-Object {
    $rel = $_.FullName.Substring($ProjectDir.Length).TrimStart('\')
    $dest = Join-Path $TempDir $rel
    if ($_.PSIsContainer) {
        if (-not (Test-Path $dest)) { New-Item -Path $dest -ItemType Directory -Force | Out-Null }
    } else {
        $destDir = Split-Path $dest -Parent
        if (-not (Test-Path $destDir)) { New-Item -Path $destDir -ItemType Directory -Force | Out-Null }
        Copy-Item $_.FullName $dest -Force
    }
}

Write-Host "[2/3] Compressing to zip..."
Compress-Archive -Path "$TempDir\*" -DestinationPath $ZipPath -Force

Write-Host "[3/3] Cleaning up..."
Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "========================================"
if (Test-Path $ZipPath) {
    $size = (Get-Item $ZipPath).Length
    $sizeKB = [math]::Round($size / 1024)
    Write-Host "  OK - Backup created"
    Write-Host "  File: $ZipPath"
    Write-Host "  Size: ${sizeKB} KB"
} else {
    Write-Host "  FAILED - Check errors above"
}
Write-Host "========================================"
Write-Host ""
Read-Host "Press Enter to exit"
