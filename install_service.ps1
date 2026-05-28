# Agent Team Windows Service Installer
# Requires NSSM: https://nssm.cc/download

# ========== CONFIGURATION ==========
$WORKDIR = "D:\Users\lenovo\Desktop\claude workspace"
$PYTHON_EXE = "C:\Users\lenovo\AppData\Local\Programs\Python\Python311\python.exe"
$SERVICE_NAME = "AgentTeam"
# ===================================

# Check admin rights
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: Run as Administrator!" -ForegroundColor Red
    pause
    exit 1
}

$Script = Join-Path $WORKDIR "run_agent.py"
$LogDir = Join-Path $WORKDIR "logs"

# Create logs directory
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "=== AgentTeam Service Installation ===" -ForegroundColor Cyan
Write-Host "Workspace: $WORKDIR"
Write-Host "Python: $PYTHON_EXE"
Write-Host "Logs: $LogDir"
Write-Host ""

# Validate files
if (-not (Test-Path $Script)) {
    Write-Host "ERROR: Script not found - $Script" -ForegroundColor Red
    pause
    exit 1
}
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "ERROR: Python not found - $PYTHON_EXE" -ForegroundColor Red
    pause
    exit 1
}

$NSSM_EXE = "C:\Windows\System32\nssm.exe"

# Remove old service
Write-Host "Cleaning old service..." -ForegroundColor Gray
& $NSSM_EXE stop $SERVICE_NAME 2>$null
Start-Sleep -Seconds 2
& $NSSM_EXE remove $SERVICE_NAME confirm 2>$null

# Install new service
Write-Host "Installing..." -ForegroundColor Green
& $NSSM_EXE install $SERVICE_NAME $PYTHON_EXE

if ($LASTEXITCODE -ne 0) {
    Write-Host "Installation failed!" -ForegroundColor Red
    pause
    exit 1
}

# Set parameters: 传递脚本路径和工作区路径两个参数
# 使用单引号包裹路径，避免引号转义问题
$Script = Join-Path $WORKDIR "run_agent.py"
$params = "'$Script' '$WORKDIR'"
& $NSSM_EXE set $SERVICE_NAME AppParameters $params 2>$null
if ($LASTEXITCODE -ne 0) {
    # 方法1失败，尝试方法2：只传脚本路径（依赖 AppDirectory）
    & $NSSM_EXE set $SERVICE_NAME AppParameters "run_agent.py" 2>$null
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "Installation failed!" -ForegroundColor Red
    pause
    exit 1
}

# Configure service
& $NSSM_EXE set $SERVICE_NAME Start SERVICE_AUTO_START
& $NSSM_EXE set $SERVICE_NAME AppDirectory $WORKDIR
& $NSSM_EXE set $SERVICE_NAME AppRestartDelay 5000

# Restart on non-zero exit
& $NSSM_EXE set $SERVICE_NAME AppExit 0 Exit
& $NSSM_EXE set $SERVICE_NAME AppExit 1 Restart
& $NSSM_EXE set $SERVICE_NAME AppExit 2 Restart
& $NSSM_EXE set $SERVICE_NAME AppExit 3 Restart

# Log redirection
$StdoutLog = Join-Path $LogDir "stdout.log"
$StderrLog = Join-Path $LogDir "stderr.log"

& $NSSM_EXE set $SERVICE_NAME AppStdout $StdoutLog
& $NSSM_EXE set $SERVICE_NAME AppStderr $StderrLog
& $NSSM_EXE set $SERVICE_NAME AppStdoutCreationDisposition 4
& $NSSM_EXE set $SERVICE_NAME AppStderrCreationDisposition 4

# Daily rotation
& $NSSM_EXE set $SERVICE_NAME AppRotateFiles 1
& $NSSM_EXE set $SERVICE_NAME AppRotateOnline 1
& $NSSM_EXE set $SERVICE_NAME AppRotateSeconds 86400

# Description
& $NSSM_EXE set $SERVICE_NAME Description "Agent Team AI Assistant"

Write-Host ""
Write-Host "SUCCESS! Service installed." -ForegroundColor Green
Write-Host ""
Write-Host "Commands:" -ForegroundColor Cyan
Write-Host "  $NSSM_EXE start $SERVICE_NAME"
Write-Host "  $NSSM_EXE stop $SERVICE_NAME"
Write-Host "  $NSSM_EXE status $SERVICE_NAME"
Write-Host "  $NSSM_EXE edit $SERVICE_NAME"
Write-Host ""
Write-Host "Logs:" -ForegroundColor Cyan
Write-Host "  $StdoutLog"
Write-Host "  $StderrLog"
Write-Host ""
Write-Host "Start with: $NSSM_EXE start $SERVICE_NAME" -ForegroundColor Yellow
Write-Host ""
pause
