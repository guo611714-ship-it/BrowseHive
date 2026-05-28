# Agent Team 服务快速启动指南

## 问题诊断

当前服务状态：`STOPPED`
原因：NSSM 参数配置错误（AppParameters 包含空格导致解析失败）

## 修复步骤（需要管理员权限）

### 方法 1 - 使用 PowerShell 脚本（推荐）

以 **管理员身份** 运行 PowerShell，执行：

```powershell
cd "D:\Users\lenovo\Desktop\claude workspace"

# 清理旧服务（如果存在）
nssm remove AgentTeam confirm 2>$null

# 安装新服务
nssm install AgentTeam "C:\Python311\python.exe"

# 设置参数
nssm set AgentTeam AppParameters "run_agent.py"
nssm set AgentTeam AppDirectory "D:\Users\lenovo\Desktop\claude workspace"

# 设置自启动
nssm set AgentTeam Start SERVICE_AUTO_START

# 设置重启延迟
nssm set AgentTeam AppRestartDelay 5000

# 配置日志重定向
$LogDir = "D:\Users\lenovo\Desktop\claude workspace\logs"
nssm set AgentTeam AppStdout "$LogDir\stdout.log"
nssm set AgentTeam AppStderr "$LogDir\stderr.log"
nssm set AgentTeam AppRotateSeconds 86400

# 启动服务
nssm start AgentTeam

# 查看状态
nssm status AgentTeam
```

### 方法 2 - 运行现有安装脚本

以管理员身份运行：
```powershell
.\install_service.ps1
```

该脚本会重新安装并启动服务。

### 方法 3 - CLI 模式（无需服务）

如果只需要临时测试，直接运行：
```powershell
python run_agent.py
```

## 验证启动

```powershell
# 查看服务状态
nssm status AgentTeam

# 查看实时日志
Get-Content .\logs\stdout.log -Wait

# 或查看主日志
Get-Content .\logs\agent_$(Get-Date -Format 'yyyy-MM-dd').log -Wait
```

## 常见问题

| 问题 | 解决 |
|------|------|
| 服务无法启动 | 检查 `.\logs\stderr.log` |
| 找不到 Python | 确认 `C:\Python311\python.exe` 存在，或修改路径 |
| 配置文件错误 | 检查 `model_config.json` 格式 |
| 权限错误 | 确保以管理员运行 |

## 预期输出

启动成功后，日志应显示：
```
============================================================
Agent Team 启动
时间: 2026-05-27 HH:MM:SS
工作区: D:\Users\lenovo\Desktop\claude workspace
日志: ...\logs\agent_2026-05-27.log
============================================================

[OK] lead teammate 使用模型: nvidia/minimaxai/minimax-m2.7
[INFO] 启动主循环 (尝试 1)
[*] Agent 已启动，输入 /exit 退出
```
