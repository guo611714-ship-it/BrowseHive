# Chrome CDP Launcher - 启动带远程调试端口的Chrome
# 用法: powershell -ExecutionPolicy Bypass -File chrome-cdp-launcher.ps1 [-Port 9222]

param(
    [int]$Port = 9222,
    [string]$UserDataDir = "$env:LOCALAPPDATA\ms-playwright\mcp-chrome-persistent"
)

$chromePath = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty "(default)"
if (-not $chromePath) {
    $chromePath = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
}
if (-not (Test-Path $chromePath)) {
    $chromePath = "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe"
}

if (-not (Test-Path $chromePath)) {
    Write-Error "Chrome not found"
    exit 1
}

# 检查端口是否已被占用
$existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Port $Port already in use. Chrome CDP may already be running."
    Write-Host "PID: $($existing[0].OwningProcess)"
    exit 0
}

Write-Host "Launching Chrome with CDP on port $Port..."
Write-Host "User data: $UserDataDir"

Start-Process $chromePath -ArgumentList @(
    "--remote-debugging-port=$Port",
    "--remote-debugging-address=127.0.0.1",
    "--user-data-dir=$UserDataDir",
    "--no-first-run",
    "--disable-features=TranslateUI",
    "--disable-sync",
    "--disable-component-update"
)

# 等待CDP端口就绪
$maxWait = 10
for ($i = 0; $i -lt $maxWait; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/json/version" -UseBasicParsing -TimeoutSec 2
        Write-Host "CDP ready at http://127.0.0.1:$Port"
        Write-Host "Browser: $($response.Content | ConvertFrom-Json).Browser"
        exit 0
    } catch {
        Write-Host "Waiting for CDP... ($($i+1)/$maxWait)"
    }
}

Write-Warning "CDP not ready after ${maxWait}s. Check Chrome manually."
exit 1
