# Agent Team Windows 服务部署指南

## 目录
- [快速开始](#快速开始)
- [详细步骤](#详细步骤)
- [故障排查](#故障排查)
- [日志管理](#日志管理)
- [高级配置](#高级配置)

---

## 快速开始

1. **安装 NSSM**（如果还未安装）
   - 下载: https://nssm.cc/download
   - 解压后复制 `nssm.exe` 到 `C:\Windows\System32\`

2. **修改配置文件**
   - 编辑 `install_service.ps1`，设置你的工作区和 Python 路径

3. **以管理员身份运行**
   ```powershell
   cd "D:\Users\lenovo\Desktop\claude workspace"
   .\install_service.ps1
   ```

4. **启动服务**
   ```powershell
   nssm start AgentTeam
   ```

5. **验证**
   ```powershell
   nssm status AgentTeam
   # 或检查日志文件
   ```

---

## 详细步骤

### 1. 环境要求
- Windows 10/11
- Python 3.9+（建议 3.11）
- NVIDIA API Key 已配置（model_config.json）
- `agent` 代码已就绪

### 2. 准备工作区
确认以下文件在正确位置：
```
工作区/
├── agent/                    # 源代码
├── model_config.json         # 模型配置
├── .team/config.json         # 团队配置
├── templates/                # 提示词模板
├── memory/                   # 持久化存储（自动创建）
├── logs/                     # 运行日志（自动创建）
└── run_agent.py              # 启动脚本（已创建）
```

### 3. 配置 run_agent.py

确认 `run_agent.py` 中的参数正确（默认使用 `Path.cwd()`）。

### 4. 安装为服务

**方法 A - 使用 PowerShell 脚本（推荐）**

```powershell
# 1. 修改配置
notepad .\install_service.ps1
# 设置 WORKDIR 和 PYTHON_EXE

# 2. 以管理员身份运行
PowerShell -ExecutionPolicy Bypass -File .\install_service.ps1
```

**方法 B - 手动配置 NSSM**

```cmd
nssm install AgentTeam "C:\Python311\python.exe" "D:\path\to\run_agent.py"
nssm set AgentTeam Start SERVICE_AUTO_START
nssm set AgentTeam AppDirectory "D:\path\to\workspace"
nssm set AgentTeam AppRestartDelay 5000
```

### 5. 服务管理命令

| 命令 | 功能 |
|------|------|
| `nssm start AgentTeam` | 启动 |
| `nssm stop AgentTeam` | 停止 |
| `nssm restart AgentTeam` | 重启 |
| `nssm status AgentTeam` | 查看状态 |
| `nssm edit AgentTeam` | 编辑配置 |
| `nssm remove AgentTeam confirm` | 卸载 |

---

## 故障排查

### 服务无法启动

1. 检查 NSSM 是否正确安装：
   ```powershell
   nssm version
   ```

2. 检查 Python 路径：
   ```powershell
   "C:\Python311\python.exe" --version
   ```

3. 检查脚本权限：
   ```powershell
   Get-Acl run_agent.py | Format-List
   ```

4. 查看服务错误日志：
   ```powershell
   # NSSM 自身日志
   Get-Content "$env:ProgramData\NSSM\nssm.log" -Tail 50
   
   # Agent 输出日志
   Get-Content ".\logs\service_stderr.log" -Tail 50
   ```

### 常见问题

| 问题 | 解决方案 |
|------|---------|
| 4007 错误（路径含空格） | 使用英文双引号包裹路径，install_service.ps1 已处理 |
| 服务启动后立即停止 | 查看 `logs/service_stderr.log`，通常是 Python 环境问题 |
| 无法导入 agent 模块 | 确保工作区路径正确，Python 能访问 `agent/` 目录 |
| NVIDIA API 无效 | 检查 `model_config.json` 中的 `providers.nvidia.apiKey` |
| 日志文件为空 | 检查 NSSM I/O 重定向配置是否正确 |

---

## 日志管理

### 日志文件
```
logs/
├── agent_2025-05-27.log        # 主日志（run_agent.py 输出）
├── agent_error_2025-05-27.log  # 错误日志
├── stdout.log                  # NSSM 标准输出（滚动）
└── stderr.log                  # NSSM 错误输出（滚动）
```

### 日志轮转
- NSSM 默认每 24 小时（86400 秒）自动滚动
- 也可配置为按大小滚动（需修改 NSSM 配置）

### 查看实时日志
```powershell
# PowerShell
Get-Content ".\logs\stdout.log" -Wait

# 或使用 BareTail 等工具（推荐）
```

---

## 高级配置

### 调整重启行为

```powershell
# 修改重启延迟（秒）
nssm set AgentTeam AppRestartDelay 30000  # 30秒

# 更激进的重试策略
nssm set AgentTeam AppExit 0 Restart
```

### 限制内存使用（可选）

在 `nssm edit AgentTeam` 中设置：
```
I/O 重定向:
  Output (stdout): 已配置
  Error (stderr): 已配置
  I/O 优先级: 低
```

### 监控服务健康

创建 `check_agent.bat`：

```batch
@echo off
nssm status AgentTeam >nul
if errorlevel 1 (
    echo [ALERT] AgentTeam 服务未运行！
    exit 1
)
echo [OK] AgentTeam 运行正常
exit 0
```

搭配 Windows 任务计划程序或监控系统（Zabbix/Prometheus+node_exporter）。

---

## 服务安装验证清单

- [ ] NSSM 已安装并可访问
- [ ] Python 路径正确
- [ ] `run_agent.py` 可独立运行（测试：`python run_agent.py`）
- [ ] `model_config.json` 配置有效（API Key 非空）
- [ ] `install_service.ps1` 中的路径已修改
- [ ] 以管理员身份执行安装脚本
- [ ] 服务显示 `SERVICE_RUNNING` 状态
- [ ] 日志文件正常写入

---

## 下一步

安装完成后：
1. 使用 `/team` 验证队友状态
2. 使用 `/status` 查看系统状态
3. 配置日常备份（memory 目录）
4. 设置监控告警（服务异常重启时通知）
