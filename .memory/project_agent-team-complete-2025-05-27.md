---
name: project-agent-team-complete-2025-05-27
description: Agent Team 完整项目档案：功能、使用指南、CodeGraph 索引、NSSM 部署
metadata:
  type: project
---

## 项目概览

**Agent Team** 是一个多智能体协作的 AI 助手系统，支持：
- 主 Agent + 固定队友团队（lead/coder/researcher/reviewer/reader）
- 子代理派遣（轻量只读、文档阅读、搜索、质检、工程执行）
- 多模型路由（NVIDIA/DeepSeek/Anthropic/OpenAI）
- 完整工具集（文件、shell、web、技能、任务管理）
- Windows 服务部署（NSSM 后台持久运行）

---

## 核心架构

```
AgentLoop (主循环)
├── MemoryStore (持久化记忆)
├── TeamStore (团队配置管理)
├── ContextAssembler (提示词构建)
└── ModelOrchestrator (模型路由)
    └── LLMClient (多供应商统一接口)
        ├── _call_deepseek()
        ├── _call_anthropic()
        └── _call_openai()
```

---

## 功能特性

### 1. 智能体团队
- **固定队友**：lead（领导）、coder（工程师）、researcher（研究员）、reviewer（审查员）、reader（阅读员）
- **动态创建**：支持 `/spawn_teammate` 创建新队友
- **消息总线**：TeamStore + MessageBus 实现 teammate 间通信

### 2. 模型编排
- 根据 teammate 配置自动选择模型
- 支持二级回退（指定模型无效 → 默认模型）
- 客户端池缓存复用

### 3. 工具系统
| 工具模块 | 功能 |
|---------|------|
| `file_tools` | 读写文件、glob 搜索 |
| `shell_tools` | 执行命令 |
| `web_tools` | 抓取网页 |
| `search_tools` | 搜索 |
| `skill_tools` | 加载自定义技能 |
| `todo_tools` | 任务清单管理 |
| `dispatch_tools` | 派遣子代理 |
| `team_tools` | 团队管理 |

### 4. 权限模式
- **ask_before_edit**：编辑前需审批
- **auto**：全自动执行
- **plan**：计划模式（先规划再执行）

---

## 服务部署（Windows NSSM）

### 安装
```powershell
# 以管理员运行 PowerShell
cd "D:\Users\lenovo\Desktop\claude workspace"
.\install_service.ps1
```

### 配置参数
- **Application**: `C:\Python311\python.exe`
- **AppParameters**: `"D:\...\run_agent.py" "D:\...\claude workspace"`（脚本路径 + 工作区）
- **AppDirectory**: `D:\Users\lenovo\Desktop\claude workspace`
- **Start**: `SERVICE_AUTO_START`
- **日志**: `logs\stdout.log` / `logs\stderr.log`（覆盖模式 `CreationDisposition=4`）

### 管理命令
```powershell
nssm start AgentTeam    # 启动
nssm stop AgentTeam     # 停止
nssm status AgentTeam   # 状态
nssm restart AgentTeam  # 重启
```

---

## 使用指南

### 服务启动后

1. **验证服务运行**
   ```powershell
   nssm status AgentTeam  # 应显示 SERVICE_RUNNING
   ```

2. **查看服务日志**
   ```powershell
   Get-Content .\logs\stdout.log -Wait
   ```

   预期看到：
   ```
   [OK] lead teammate 使用模型: nvidia/minimaxai/minimax-m2.7
   [INFO] 启动主循环 (尝试 1)
   [*] Agent 已启动，输入 /exit 退出
   ```

### 发送任务给 Agent

Agent Team 作为后台服务运行，可通过以下方式交互：

#### 方式 A：文件消息队列
```powershell
# 向 lead teammate 发送消息
$msg = @{
    from = "user"
    content = "请分析这个项目结构"
    timestamp = (Get-Date).ToString("o")
} | ConvertTo-Json
$msg | Out-File -Append .team/inbox/lead.jsonl -Encoding utf8

# 查看回复
Get-Content .team/outbox/lead.jsonl
```

#### 方式 B：通过 Claude Code MCP（如已集成）
在 Claude Code 中输入：
```
@AgentTeam 帮我查看当前团队状态
```

### 常用操作

| 操作 | 方法 |
|------|------|
| 查看队友列表 | 读取 `.team/config.json` 或调用 `team_tools.list_teammates()` |
| 发送消息 | 追加到 teammate 的 inbox JSONL |
| 读取结果 | 读取 teammate 的 outbox JSONL |
| 停止服务 | `nssm stop AgentTeam` |
| 重启服务 | `nssm restart AgentTeam` |

---

## CodeGraph 索引状态

已为 Agent Team 项目建立完整知识图谱：

```
索引时间: 2025-05-27 12:41
文件数: 21,141
节点数: 193,314
边数: 172,595
数据库: 905.63 MB
主要语言: JavaScript (15k), TypeScript (5.4k), Python (208)
```

关键符号类型：
- `function`: 22,688
- `class`: 4,044
- `method`: 26,117
- `variable`: 39,220

---

## 配置说明

### model_config.json
```json
{
  "agents": {
    "defaults": {
      "model": "nvidia-gemma",
      "provider": "nvidia",
      "maxTokens": 512,
      "temperature": 0.2
    }
  },
  "providers": {
    "nvidia": { "apiKey": "...", "apiBase": "https://integrate.api.nvidia.com/v1" }
  }
}
```

### .team/config.json
```json
{
  "teammates": [
    { "name": "lead", "role": "领导", "agent_type": "manager", "status": "idle" },
    { "name": "coder", "role": "工程师", "agent_type": "coder" }
  ]
}
```

---

## 已知限制与待办

- [ ] 提供 HTTP API 接口（替代文件队列）
- [ ] 添加更完善的监控端点（`/health`, `/metrics`）
- [ ] 日志自动轮转清理策略
- [ ] TeamStore 初始化异常保护

---

## 故障排查

| 问题 | 检查 |
|------|------|
| 服务无法启动 | `logs/stderr.log` |
| 无响应 | 检查 `model_config.json` API Key |
| 频繁重启 | 查看 `logs/agent_*.log` 异常堆栈 |
| 内存占用高 | 限制 `max_tokens` 或重启服务 |

---

## 参考链接

- 代码审查报告: `.claude/projects/code-review-2025-05-27.json`
- 修复记录: `.claude/projects/code-review-findings.json`
- 部署文档: `DEPLOY_WINDOWS.md`
- 快速启动: `QUICK_START_SERVICE.md`

---

**最后更新**: 2025-05-27  
**状态**: ✅ 服务运行中，知识图谱已更新
