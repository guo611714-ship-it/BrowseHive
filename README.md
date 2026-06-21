# Agent Team — 多模型协作AI代理系统

[![CI](https://github.com/user/agent-team/actions/workflows/ci.yml/badge.svg)](https://github.com/user/agent-team/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-492%20passed-brightgreen.svg)]

## 架构概览

```
Claude Code REPL + Skills
    │
    ▼
AgentLoop ─── 6子代理 + 4调度模式 + 28工具
    │
    ├── ModelOrchestrator ── 10模型路由 (复杂度/场景/角色)
    ├── MemoryStore ──────── 3层记忆 (工作/情景/长期)
    ├── KnowledgeService ─── 结构化KB + DeepWiki 325K索引
    └── EventBus ─────────── 组件解耦通信
            │
            ▼
    5 MCP Servers (ai-chat / codegraph / context7 / github / chrome-devtools)
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境
cp .env.example .env
# 编辑 .env 填入 NVIDIA_API_KEY 等

# 3. 启动 Agent
python agent/loop.py

# 4. 启动 MCP 服务 (可选)
node MCP/server.js
```

## 目录结构

```
agent/                  # 核心 Agent 包
  loop.py               # AgentLoop 主循环
  model_orchestrator.py  # 10模型智能路由
  llm_client.py          # LLM 调用客户端
  knowledge_service.py   # 知识服务统一接口
  memory.py              # 3层记忆系统
  tools/                 # 28个工具 (注册即用)
    tool_registry.py     # @tool 装饰器自动生成 Schema
    browser_tools.py     # 浏览器AI联邦 (4平台)
    deepwiki_tools.py    # DeepWiki 集成
    dispatch/            # 4种调度模式
  subagents/             # 6种子代理 (朝廷命名)
  kb/                    # 知识库包 (原 kb_*.py)

AI知识库/               # Obsidian 兼容知识库
  raw/sources/deepwiki/  # DeepWiki 325K项目索引

MCP/                    # 5个 MCP Server
  scripts/ai-chat-mcp.py  # 多平台AI聊天 (76工具)
  scripts/browser_agent.py # 浏览器代理
  scripts/codegraph/       # 代码知识图谱

memory/                 # 运行时记忆
tests/                  # 492个测试
templates/              # 系统提示词模板
shared/                 # 共享工具 (RateLimiter, ApiKeyPool)
```

## 子代理角色

| 代号 | 名称 | 职责 | 模型 |
|------|------|------|------|
| xiaohuangmen | 通传小黄门 | 轻量只读 | step-3.7-flash |
| sili_suitang | 司礼监随堂 | 文档阅读 | step-3.7-flash |
| dongchang_tanshi | 东厂探事 | 网络搜索 | step-3.7-flash |
| shangbao_dianbu | 尚宝监典簿 | 质量审计 | mistral-nemotron |
| neiguan_yingzao | 内官监营造 | 工程执行 | minimax-m2.7 |
| browser_agent | 浏览器操作员 | 网页操作 | step-3.7-flash |

## 模型路由

10个模型按复杂度自动路由：

| 复杂度 | 模型 | 用途 |
|--------|------|------|
| 1 | gemma-e2b | 极轻量任务 |
| 2 | step-3.7-flash | 子代理默认 |
| 3 | minimax-m2.7 | Agent执行 |
| 4 | mistral-large-3 | 推理分析 |
| 5 | glm-5.1 | 深度推理 |

## 工具系统

```python
from agent.tools.tool_registry import tool

@tool("my_tool", "工具描述")
async def my_tool(param: str) -> dict:
    """自动从类型注解生成 JSON Schema"""
    return {"result": param}
```

## 开发

```bash
# 运行全部测试
pytest tests/ -v

# 类型检查
mypy agent/ --strict

# 代码检查
ruff check agent/

# 覆盖率
pytest tests/ --cov=agent --cov-report=html
```

## 许可证

MIT
