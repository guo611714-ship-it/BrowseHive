# CodeGraph 维护脚本 v2
# 用法:
#   maintain-codegraph.ps1           # 索引 + 优化
#   maintain-codegraph.ps1 -Force    # 强制重建
#   maintain-codegraph.ps1 -OptimizeOnly  # 仅优化 PRAGMA

param(
    [switch]$Force,
    [switch]$OptimizeOnly
)

$projectDir = 'D:\Users\lenovo\Desktop\claude workspace'
$dbPath = Join-Path $projectDir '.codegraph\codegraph.db'
$optimizeScript = Join-Path $projectDir 'scripts\optimize-codegraph.js'

function Optimize-Database {
    node $optimizeScript $dbPath
}

if (-not (Test-Path $dbPath)) {
    Write-Host 'Database not found, initializing...'
    codegraph init $projectDir 2>&1 | Out-Null
    codegraph index $projectDir 2>&1 | Out-Null
    Optimize-Database
    Write-Host 'Init + optimize done' -ForegroundColor Green
    exit 0
}

$sizeMB = [math]::Round((Get-Item $dbPath).Length / 1MB, 1)
Write-Host "Current DB: $sizeMB MB"

if ($Force) {
    Write-Host 'Force rebuild...'
    Remove-Item (Join-Path $projectDir '.codegraph') -Recurse -Force
    codegraph init $projectDir 2>&1 | Out-Null
    codegraph index $projectDir 2>&1 | Out-Null
    Optimize-Database
    $newSize = [math]::Round((Get-Item $dbPath).Length / 1MB, 1)
    Write-Host "Rebuilt: $newSize MB (saved $([math]::Round($sizeMB - $newSize, 1)) MB)" -ForegroundColor Green
    exit 0
}

if ($OptimizeOnly) {
    Optimize-Database
    $newSize = [math]::Round((Get-Item $dbPath).Length / 1MB, 1)
    Write-Host "Optimized: $newSize MB" -ForegroundColor Green
    exit 0
}

Write-Host 'Indexing...'
codegraph index $projectDir 2>&1 | Out-Null

Write-Host 'Optimizing...'
Optimize-Database

$newSize = [math]::Round((Get-Item $dbPath).Length / 1MB, 1)
$saved = [math]::Round($sizeMB - $newSize, 1)
if ($saved -gt 0) {
    Write-Host "Done: $newSize MB (saved $saved MB)" -ForegroundColor Green
} else {
    Write-Host "Done: $newSize MB" -ForegroundColor Green
}
