@echo off
REM AI Chat MCP HTTP Server - 后台启动
REM 端口: 8090

tasklist /FI "WINDOWTITLE eq ai-chat-mcp*" 2>NUL | findstr /I "python" >NUL
if %ERRORLEVEL% == 0 (
    echo [ai-chat] Already running
    exit /b 0
)

echo [ai-chat] Starting HTTP server on port 8090...
start /B /MIN "ai-chat-mcp" python "D:\Users\lenovo\Desktop\claude workspace\MCP\start-ai-chat-http.py"
echo [ai-chat] Started
