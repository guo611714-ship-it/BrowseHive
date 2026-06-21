---
name: project-agent-team-2025-05-27
description: Agent Team AI助手系统：多智能体协作架构、模型编排、Windows服务部署
metadata:
  type: project
---

## 项目概述

**Agent Team** 是一个多智能体协作的 AI 助手系统，支持：
- 主 Agent 与多个固定队友（lead/coder/researcher/reviewer/reader）协作
- 子代理派遣（轻量只读、文档阅读、搜索、质检、工程执行）
- 多模型路由（NVIDIA/DeepSeek/Anthropic/OpenAI）
- 工具调度与权限管理
- Windows NSSM 服务部署

## 核心架构

### 目录结构
```
workspace/
├── agent/                    # 核心代码
│   ├── loop.py              # 主循环，组件装配
│   ├── model_orchestrator.py # 模型路由与客户端池
│   ├── llm_client.py        # 统一 LLM 接口（多供应商）
│   ├── runner.py            # Agent 执行器
│   ├── memory.py            # 持久化存储
│   ├── context.py           # 上下文组装
│   ├── team_store.py        # 团队配置管理
│   └── tools/               # 内置工具集
├── model_config.json        # 模型与供应商配置
├── .team/                   # 团队状态（自动生成）
├── memory/                  # 对话记忆（自动生成）
├── templates/               # 提示词模板
├── run_agent.py             # Windows 服务启动器
└── install_service.ps1      # NSSM 服务安装脚本
```

### 关键组件

**1. AgentLoop** (`loop.py`)
- 负责所有组件装配和对话管理
- 初始化：`MemoryStore` + `TeamStore` + `ContextAssembler` + `ModelOrchestrator`
- 主循环：用户输入 → LLM 调用 → 工具执行 → 结果返回

**2. ModelOrchestrator** (`model_orchestrator.py`)
- 模型路由器与客户端池
- 根据 teammate 配置路由到指定模型
- 支持二级回退（指定模型无效 → 默认模型）
- 客户端缓存复用

**3. LLMClient** (`llm_client.py`)
- 统一接口支持：DeepSeek / Anthropic / OpenAI / NVIDIA
- HTTP 调用 + 异常处理 + 响应解析
- 流式请求暂未启用

**4. TeamStore**
- 管理 teammate 配置（name/role/agent_type/status/model）
- Inbox 消息文件（JSONL 格式）
- 团队通信 via `MessageBus`

**5. 工具系统**
- 文件工具：`file_tools`（read/write/edit/glob）
- Shell 工具：`shell_tools`（命令执行）
- Web 工具：`web_tools`（fetch/search）
- 派遣工具：`dispatch_tools`（子代理 + spawn_teammate）
- 技能工具：`skill_tools`（自定义技能加载）
- Todo 工具：`todo_tools`（任务清单）

## 配置说明

### model_config.json 结构
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
  "models": [
    {
      "name": "...",
      "provider": "...",
      "mainModelId": "...",
      "apiKey": "",
      "apiBase": "..."
    }
  ],
  "providers": {
    "nvidia": { "apiKey": "...", "apiBase": "..." },
    "deepseek": { "apiKey": "", "apiBase": "..." }
  }
}
```

### .team/config.json（示例）
```json
{
  "teammates": [
    { "name": "lead", "role": "领导", "agent_type": "manager", "status": "idle" },
    { "name": "coder", "role": "工程师", "agent_type": "coder", "model": "nvidia-gemma" },
    ...
  ]
}
```

## 部署方式

### Windows NSSM 服务（推荐生产环境）
```powershell
# 1. 修改 install_service.ps1 中的路径
# 2. 以管理员运行
.\install_service.ps1

# 3. 启动服务
nssm start AgentTeam

# 4. 查看状态
nssm status AgentTeam

# 5. 查看日志
Get-Content .\logs\stdout.log -Wait
```

### CLI 模式（开发环境）
```bash
python run_agent.py [workspace_path]
# 或直接
python -m agent.loop
```

## 当前状态（2025-05-27）

- ✅ 代码审查完成，15个缺陷已修复
- ✅ ModelOrchestrator 异常处理完善
- ✅ LLM 调用健壮性提升（网络异常、响应安全检查）
- ✅ 配置类型安全（max_tokens/temperature int/float 转换）
- ✅ 日志系统从 print 切换到 logging

### 待办事项
- [ ] 为 TeamStore 初始化添加异常保护
- [ ] 配置 pydantic 模式验证
- [ ] 增加 /health 端点用于监控
- [ ] 测试 Windows 服务自启动

## 与 MCP 的关系

Agent Team 是一个**独立**的 CLI 应用，与 MCP 工作流**无直接依赖**：
- 可作为独立服务运行（NSSM Windows Service）
- 可通过 `dispatch_subagent` 工具与 MCP 子代理协作
- 不依赖 BrowseHive 或 Meta MCP 启动

## 历史变更

- **2025-05-27** - 代码审查与关键修复（启动稳定性、API 健壮性）
- **previous** - 初始版本：多智能体架构、模型路由、工具调度

## 参考文档

- `DEPLOY_WINDOWS.md` - Windows 服务部署指南
- `model_config.json` - 模型配置示例
- `.claude/projects/code-review-findings.json` - 详细审查报告
